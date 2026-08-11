"""问答路由：POST /api/qa/ask、POST /api/qa/stream（SSE流式）、GET /api/qa/history、DELETE /api/qa/{id}。"""
import asyncio
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.qa_record import QA_Record
from app.models.user import User
from app.schemas.ai import QASchema
from app.services.agents import qa_agent
from app.services.llm.client import LLMError, astream_text
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/qa", tags=["qa"])
settings = get_settings()


class QAAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _qa_record_out(rec: QA_Record) -> dict:
    return {
        "id": str(rec.id),
        "question": rec.question,
        "answer": rec.answer,
        "sources": rec.sources,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


@router.post("/ask")
async def ask(
    body: QAAskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """提问 → AI 联网搜索 + 结构化回答 → 落库。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
    out = await qa_agent.run_qa(body.question)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "生成失败，请稍后重试", code=502, status_code=502)

    answer = out["result"]
    record = QA_Record(
        user_id=user.id,
        question=body.question,
        answer=answer,
        sources=answer.get("sources"),
    )
    db.add(record)
    await record_ai_call(db, user.id, "qa", settings.DEEPSEEK_MODEL)
    await db.commit()
    await db.refresh(record)
    return ok(_qa_record_out(record))


def _extract_json_obj(text: str) -> dict:
    """从流式累积的模型输出中提取首个 JSON 对象。"""
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("模型输出中未找到 JSON")
    return json.loads(m.group(0))


async def _parse_stream_result(text: str) -> dict | None:
    """流式累积文本 → 语义校验（推荐需清单/单菜需菜名+步骤）。"""
    try:
        data = _extract_json_obj(text)
    except Exception:  # noqa: BLE001
        return None
    try:
        parsed = QASchema.model_validate(data)
        has_recs = bool(parsed.recommendations)
        has_single = bool(parsed.dish_name.strip()) and len(parsed.steps) >= 1
        if has_recs or has_single:
            return data
    except Exception:  # noqa: BLE001
        pass
    return None


@router.post("/stream")
async def ask_stream(
    body: QAAskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式问答：模型逐字输出 → SSE。打字机显示核心秘诀，完成后渲染结构化卡片。

    流程：流式收集完整 JSON → 语义校验 → 落库 → SSE 返回。
    SSE 事件：
      {"type":"delta","text":"核心秘诀的逐字片段"}
      {"type":"done","data":{...结构化回答...}}
    """
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    async def event_stream():
        # 流式收集完整模型输出
        buf = ""
        try:
            async for delta in astream_text(
                model=settings.DEEPSEEK_MODEL,
                system=qa_agent.QA_SYSTEM,
                user=body.question,
                enable_search=settings.AI_ENABLE_SEARCH,
                search_options={"forced_search": True},
            ):
                buf += delta
        except LLMError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        data = await _parse_stream_result(buf)
        if data is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 回答生成失败，请稍后重试'})}\n\n"
            return

        # 落库
        record = QA_Record(
            user_id=user.id,
            question=body.question,
            answer=data,
            sources=data.get("sources"),
        )
        db.add(record)
        await record_ai_call(db, user.id, "qa", settings.DEEPSEEK_MODEL)
        await db.commit()
        await db.refresh(record)

        out = _qa_record_out(record)

        # 打字机：逐字下发核心秘诀（单菜型）或推荐菜名（多菜型）
        if data.get("recommendations"):
            typing_text = "小伴为你推荐：" + "、".join(r["name"] for r in data["recommendations"])
        else:
            typing_text = data.get("dish_name", "") + "，" + (data.get("core_secret") or "")
        for ch in typing_text:
            yield f"data: {json.dumps({'type': 'delta', 'text': ch})}\n\n"
            await asyncio.sleep(0.03)

        yield f"data: {json.dumps({'type': 'done', 'data': out}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history")
async def history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """最近 20 条问答历史。"""
    result = await db.execute(
        select(QA_Record)
        .where(QA_Record.user_id == user.id)
        .order_by(QA_Record.created_at.desc())
        .limit(20)
    )
    records = result.scalars().all()
    return ok([_qa_record_out(r) for r in records])


@router.delete("/{record_id}")
async def delete_record(
    record_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除单条历史（仅限本人）。"""
    result = await db.execute(
        select(QA_Record).where(QA_Record.id == record_id, QA_Record.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise AppError("记录不存在", code=404, status_code=404)
    await db.execute(delete(QA_Record).where(QA_Record.id == record_id))
    await db.commit()
    return ok(message="已删除")
