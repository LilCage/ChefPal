"""问答路由：POST /api/qa/ask、GET /api/qa/history、DELETE /api/qa/{id}。"""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.qa_record import QA_Record
from app.models.user import User
from app.services.agents import qa_agent
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
        raise AppError(out["error"] or "AI 生成失败，请稍后重试", code=502, status_code=502)

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
