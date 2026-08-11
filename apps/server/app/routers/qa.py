"""问答路由：POST /api/qa/ask、POST /api/qa/stream（SSE流式）、GET /api/qa/history、DELETE /api/qa/{id}。

RAG 集成（菜谱知识库）：
- 先向量检索 recipe_kb（HowToCook 种子 + AI 沉淀）
- 命中 → 直接返回知识库答案（免 AI 调用、不计入每日限额），响应带 kb_hit/kb_id
- 未命中 → 走 AI 联网生成，并把结果按菜名自动入库（best-effort，失败不阻断）
"""
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
from app.services import kb as kb_service
from app.services.agents import qa_agent
from app.services.llm.client import LLMError, astream_text
from app.services.llm.embedding import EmbeddingError
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/qa", tags=["qa"])
settings = get_settings()

# 多菜推荐意图的关键词：命中则优先返回多道菜，否则返回单道最佳命中
MULTI_HINT_KEYWORDS = ("推荐", "哪几道", "换换口味", "有什么好做", "来几道", "几道菜", "想吃")


class QAAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _qa_record_out(rec: QA_Record) -> dict:
    answer = rec.answer or {}
    return {
        "id": str(rec.id),
        "question": rec.question,
        "answer": answer,
        "sources": rec.sources,
        "kb_hit": bool(answer.get("kb_hit", False)),
        "kb_id": answer.get("kb_id"),
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


# ---------- 知识库命中 → 结构化答案 ----------

def _single_recipe_answer(entry) -> dict:
    return {
        "core_secret": entry.summary or (entry.tips[0] if entry.tips else ""),
        "dish_name": entry.title,
        "ingredients": entry.ingredients,
        "steps": entry.steps,
        "prep_steps": entry.prep_steps,
        "cook_steps": entry.cook_steps,
        "avoid_pitfalls": entry.tips,
        "sources": [],
        "recommendations": None,
        "kb_hit": True,
        "kb_id": str(entry.id),
    }


def _single_tip_answer(entry) -> dict:
    return {
        "core_secret": (entry.summary or entry.content or entry.title)[:300],
        "dish_name": entry.title,
        "ingredients": [],
        "steps": [],
        "avoid_pitfalls": [],
        "sources": [],
        "recommendations": None,
        "kb_hit": True,
        "kb_id": str(entry.id),
    }


def _multi_recipe_answer(recipes: list[dict]) -> dict:
    return {
        "core_secret": "",
        "dish_name": "",
        "ingredients": [],
        "steps": [],
        "avoid_pitfalls": [],
        "sources": [],
        "recommendations": [
            {
                "name": e.title,
                "core_secret": e.summary or (e.tips[0] if e.tips else ""),
                "time_minutes": e.time_minutes,
                "ingredients": e.ingredients,
                "kb_id": str(e.id),
            }
            for h in recipes
            for e in [h["entry"]]
        ],
        "kb_hit": True,
        "kb_id": None,
    }


def _kb_to_qa_answer(question: str, hits: list[dict]) -> dict | None:
    """知识库命中列表 → QASchema 字典。

    规则：多菜推荐意图且 ≥2 道菜 → 多菜；否则返回总体最高相似度条目
    （tip 命中回答技巧，recipe 命中回答单菜）。避免"怎么去腥"这类技巧问题
    被菜谱条目抢占。
    """
    if not hits:
        return None
    recipes = [h for h in hits if h["entry"].kind == "recipe"]
    if any(k in question for k in MULTI_HINT_KEYWORDS) and len(recipes) >= 2:
        return _multi_recipe_answer(recipes[:3])
    top = hits[0]
    entry = top["entry"]
    if entry.kind == "tip":
        return _single_tip_answer(entry)
    return _single_recipe_answer(entry)


async def _store_generated_to_kb(db: AsyncSession, answer: dict, record_id: UUID) -> None:
    """AI 生成结果按菜名入库（best-effort，向量服务失败静默，不阻断主流程）。"""
    try:
        if answer.get("dish_name"):
            await kb_service.upsert_kb_entry(
                db,
                kind="recipe",
                title=answer["dish_name"],
                summary=answer.get("core_secret", ""),
                ingredients=answer.get("ingredients", []),
                steps=answer.get("steps", []),
                prep_steps=answer.get("prep_steps", []),
                cook_steps=answer.get("cook_steps", []),
                tips=answer.get("avoid_pitfalls", []),
                source_type=kb_service.SOURCE_QA_ANSWER,
                source_id=str(record_id),
            )
        for r in (answer.get("recommendations") or []):
            name = (r or {}).get("name")
            if not name:
                continue
            await kb_service.upsert_kb_entry(
                db,
                kind="recipe",
                title=name,
                summary=r.get("core_secret", ""),
                ingredients=r.get("ingredients", []),
                source_type=kb_service.SOURCE_QA_ANSWER,
                source_id=str(record_id),
            )
        await db.flush()
    except EmbeddingError:
        pass  # 知识库不可用不影响问答主流程


async def _bump_hits(db: AsyncSession, hits: list[dict]) -> None:
    for h in hits:
        await kb_service.increment_hit(db, h["entry"])


async def _search_or_generate(db: AsyncSession, question: str, user_id: UUID):
    """先检索知识库；命中返回 (answer, is_kb_hit)，未命中返回 None。"""
    try:
        hits = await kb_service.search_kb(db, question)
    except EmbeddingError:
        hits = []
    answer = _kb_to_qa_answer(question, hits) if hits else None
    if answer is not None:
        await _bump_hits(db, hits[:3])
        return answer, True
    return None, False


# ---------- 接口 ----------

@router.post("/ask")
async def ask(
    body: QAAskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """提问 → 先查知识库，命中直接返回；未命中 AI 联网生成并入库。"""
    answer, is_kb = await _search_or_generate(db, body.question, user.id)
    if is_kb:
        record = QA_Record(
            user_id=user.id,
            question=body.question,
            answer=answer,
            sources=None,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return ok(_qa_record_out(record))

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
    await db.flush()  # 先拿到 record.id（source_id 溯源用）
    await _store_generated_to_kb(db, answer, record.id)
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
    """流式问答：知识库命中直接 done；未命中模型逐字输出 → SSE。

    SSE 事件：
      {"type":"delta","text":"核心秘诀的逐字片段"}
      {"type":"done","data":{...结构化回答...}}
      {"type":"error","message":"..."}
    """
    # 先查知识库（命中不占每日 AI 限额）
    try:
        kb_hits = await kb_service.search_kb(db, body.question)
    except EmbeddingError:
        kb_hits = []
    kb_answer = _kb_to_qa_answer(body.question, kb_hits) if kb_hits else None

    async def event_stream():
        if kb_answer is not None:
            await _bump_hits(db, kb_hits[:3])
            record = QA_Record(
                user_id=user.id,
                question=body.question,
                answer=kb_answer,
                sources=None,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            yield f"data: {json.dumps({'type': 'done', 'data': _qa_record_out(record)}, ensure_ascii=False)}\n\n"
            return

        await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
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

        # 落库 + AI 生成结果入库
        record = QA_Record(
            user_id=user.id,
            question=body.question,
            answer=data,
            sources=data.get("sources"),
        )
        db.add(record)
        await db.flush()  # 先拿到 record.id
        await _store_generated_to_kb(db, data, record.id)
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
