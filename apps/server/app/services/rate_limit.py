"""AI 调用风控：单用户每日限额 + ai_calls 记账。"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import AppError
from app.models.ai_call import AICall


async def count_today_calls(db: AsyncSession, user_id: UUID) -> int:
    """统计用户最近 24 小时内 AI 调用次数。"""
    since = datetime.now(timezone.utc) - timedelta(days=1)
    result = await db.execute(
        select(func.count())
        .select_from(AICall)
        .where(AICall.user_id == user_id, AICall.created_at >= since)
    )
    return int(result.scalar_one())


async def ensure_within_limit(db: AsyncSession, user_id: UUID, limit: int) -> None:
    """超出每日限额抛 429。"""
    if limit <= 0:
        return
    if await count_today_calls(db, user_id) >= limit:
        raise AppError("今日 AI 调用已达上限，明日再来吧", code=429, status_code=429)


async def record_ai_call(db: AsyncSession, user_id: UUID, call_type: str, model: str) -> None:
    """写一条 AI 调用流水，用于成本与风控。"""
    db.add(AICall(user_id=user_id, call_type=call_type, model=model))
