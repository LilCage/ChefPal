"""购物清单路由：POST /api/shopping-list/generate、GET /latest、PUT /{id}/items/{item_id}/checked。"""
import copy
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.meal_plan import MealPlan
from app.models.shopping_list import ShoppingList
from app.models.user import User
from app.services import shopping as shopping_service
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/shopping-list", tags=["shopping-list"])
settings = get_settings()


class ShoppingGenerateRequest(BaseModel):
    meal_plan_id: UUID | None = None  # 可选：指定来源膳食计划，缺省用最新一份


class ShoppingCheckRequest(BaseModel):
    checked: bool  # 勾选/取消勾选


def _list_out(item: ShoppingList) -> dict:
    return {
        "id": str(item.id),
        "data": item.data,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _enrich_items(data: dict) -> dict:
    """给 AI 生成的每项补 item_id（勾选态用）与初始 checked=False。"""
    for cat in data.get("categories", []):
        for it in cat.get("items", []):
            it["item_id"] = str(uuid.uuid4())
            it["checked"] = False
    return data


@router.post("/generate")
async def generate_shopping_list(
    body: ShoppingGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """从膳食计划生成购物清单并落库。"""
    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)

    if body.meal_plan_id:
        plan = await db.get(MealPlan, body.meal_plan_id)
        if plan is None or plan.user_id != user.id:
            raise AppError("膳食计划不存在", code=404, status_code=404)
    else:
        result = await db.execute(
            select(MealPlan)
            .where(MealPlan.user_id == user.id)
            .order_by(MealPlan.created_at.desc())
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise AppError("还没有膳食计划，请先在「膳食规划」生成", code=400, status_code=400)

    try:
        raw = await shopping_service.generate_shopping_list(plan.data)
    except shopping_service.ShoppingError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    data = _enrich_items(raw)
    item = ShoppingList(user_id=user.id, data=data)
    await record_ai_call(db, user.id, "shopping", settings.DEEPSEEK_MODEL)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ok(_list_out(item))


@router.get("/latest")
async def latest_shopping_list(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """最近一次生成的购物清单。"""
    result = await db.execute(
        select(ShoppingList)
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.created_at.desc())
        .limit(1)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise AppError("还没有购物清单，请先生成", code=404, status_code=404)
    return ok(_list_out(item))


@router.put("/{item_id}/items/{shop_item_id}/checked")
async def toggle_checked(
    item_id: UUID,
    shop_item_id: str,
    body: ShoppingCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """勾选/取消勾选清单中的某一项（就地更新 JSONB）。"""
    item = await db.get(ShoppingList, item_id)
    if item is None or item.user_id != user.id:
        raise AppError("购物清单不存在", code=404, status_code=404)

    # 必须「先拷贝再改副本」：若直接改 item.data 本身，会话内已提交值同步被改，
    # SQLAlchemy 对比新旧值会判定「无变更」而不发 UPDATE（JSONB 无 MutableDict 跟踪）。
    data = copy.deepcopy(item.data)
    found = False
    for cat in data.get("categories", []):
        for it in cat.get("items", []):
            if it.get("item_id") == shop_item_id:
                it["checked"] = body.checked
                found = True
                break
        if found:
            break
    if not found:
        raise AppError("清单项不存在", code=404, status_code=404)

    item.data = data
    await db.commit()
    return ok({"item_id": shop_item_id, "checked": body.checked})
