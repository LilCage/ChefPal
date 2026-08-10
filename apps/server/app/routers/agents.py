"""多智能体协作路由：POST /api/agents/collaborate（原型 05 屏5）。

营养师 + 大厨 + 采购三 Agent 并行输出。AI 调用按 1 次计入风控（一次接口含三次模型调用）。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.user import User
from app.services.agents import collaborate_agent
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/agents", tags=["agents"])
settings = get_settings()


class CollaborateRequest(BaseModel):
    ingredients: list[str] = Field(min_length=1, max_length=20)
    prefs: dict | None = None  # 可选：临时覆盖口味偏好


@router.post("/collaborate")
async def collaborate(
    body: CollaborateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI 主厨团：营养师+大厨+采购三个 Agent 同时输出。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    prefs = body.prefs if body.prefs is not None else (user.preferences or {})
    out = await collaborate_agent.run_collaborate(body.ingredients, prefs)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "多智能体协作失败，请稍后重试", code=502, status_code=502)

    await record_ai_call(db, user.id, "collaborate", settings.DEEPSEEK_MODEL)
    await db.commit()
    return ok(out["result"])
