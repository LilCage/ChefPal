"""膳食规划路由：POST /api/plans/generate、GET /api/plans/latest。"""
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.meal_plan import MealPlan
from app.models.user import User
from app.schemas.ai import MealPlanSchema
from app.services.agents import planner_agent
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/plans", tags=["plans"])
settings = get_settings()


class PlanGenerateRequest(BaseModel):
    prefs: dict | None = None  # 可选：前端临时覆盖口味偏好
    days: int = Field(default=3, ge=3, le=7, description="计划天数：3（今天/明天/后天）或 7（周一~周日）")


def _plan_out(plan: MealPlan) -> dict:
    return {
        "id": str(plan.id),
        "data": plan.data,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


@router.post("/generate")
async def generate_plan(
    body: PlanGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """3/7 天膳食规划：基于用户偏好 AI 生成并落库。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    prefs = body.prefs if body.prefs is not None else (user.preferences or {})
    out = await planner_agent.run_planner(prefs, days=body.days)
    if out["error"] or out["result"] is None:
        raise AppError(out["error"] or "膳食计划生成失败，请稍后重试", code=502, status_code=502)

    # 归一化：补齐 fat_g/carbs_g 等默认字段，保证落库数据形状一致（API 边界兜底）
    try:
        data = MealPlanSchema.model_validate(out["result"]).model_dump()
    except Exception:  # noqa: BLE001
        raise AppError("膳食计划生成失败，请稍后重试", code=502, status_code=502)

    plan = MealPlan(user_id=user.id, data=data)
    await record_ai_call(db, user.id, "plan", settings.DEEPSEEK_MODEL)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return ok(_plan_out(plan))


@router.get("/latest")
async def latest_plan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """最近一次生成的膳食计划。"""
    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == user.id)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise AppError("还没有膳食计划，请先生成", code=404, status_code=404)
    return ok(_plan_out(plan))
