"""冰箱管家路由：食材添加 / 临期列表 / 做掉删除 / AI 组合推荐。"""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.fridge_item import FridgeItem
from app.models.user import User
from app.services import fridge as fridge_service
from app.services.fridge import compute_status, infer_shelf_days
from app.services.rate_limit import ensure_within_limit, record_ai_call

router = APIRouter(prefix="/fridge", tags=["fridge"])
settings = get_settings()


class FridgeAddRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    emoji: str | None = Field(default=None, max_length=8)
    best_before_days: int | None = Field(default=None, ge=1, le=3650)


def _item_out(item: FridgeItem, status: dict) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "emoji": item.emoji or "",
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "best_before_days": item.best_before_days,
        **status,
    }


async def _user_items(db: AsyncSession, user_id: UUID) -> list[FridgeItem]:
    result = await db.execute(
        select(FridgeItem).where(FridgeItem.user_id == user_id).order_by(FridgeItem.added_at.desc())
    )
    return list(result.scalars().all())


@router.get("")
async def list_fridge(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """食材列表：附已放/剩余天数与状态，按紧迫度升序（临期优先）。"""
    items = await _user_items(db, user.id)
    enriched = []
    for it in items:
        st = compute_status(it.added_at, it.best_before_days)
        enriched.append(_item_out(it, st))
    enriched.sort(key=lambda i: (i["status"] == "ok", i["days_left"]))
    expiring_count = sum(1 for i in enriched if i["status"] in ("now", "warn"))
    return ok({"items": enriched, "expiring_count": expiring_count})


@router.post("")
async def add_fridge_item(
    body: FridgeAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """添加食材；未指定保质期时按食材名自动推断（兜底 7 天）。"""
    name = body.name.strip()
    if not name:
        raise AppError("食材名不能为空", code=400, status_code=400)

    best_before_days = body.best_before_days or infer_shelf_days(name)
    item = FridgeItem(
        user_id=user.id,
        name=name[:32],
        emoji=(body.emoji or "")[:8],
        best_before_days=best_before_days,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    st = compute_status(item.added_at, item.best_before_days)
    return ok(_item_out(item, st))


@router.delete("/{item_id}")
async def remove_fridge_item(
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """做掉/扔掉：删除该食材。"""
    item = await db.get(FridgeItem, item_id)
    if item is None or item.user_id != user.id:
        raise AppError("食材不存在", code=404, status_code=404)
    await db.delete(item)
    await db.commit()
    return ok({"id": str(item_id), "removed": True})


@router.post("/advice")
async def fridge_advice(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI 组合推荐：优先消耗即将过期的食材。"""
    items = await _user_items(db, user.id)
    expiring = [it.name for it in items if compute_status(it.added_at, it.best_before_days)["status"] in ("now", "warn")]
    if not expiring:
        raise AppError("没有即将过期的食材，无需组合推荐", code=400, status_code=400)

    await ensure_within_limit(db, user.id, settings.DAILY_AI_LIMIT)
    all_names = [it.name for it in items]
    try:
        data = await fridge_service.generate_advice(expiring, all_names)
    except fridge_service.FridgeAdviceError as exc:
        raise AppError(str(exc), code=502, status_code=502) from exc

    await record_ai_call(db, user.id, "fridge_advice", settings.DEEPSEEK_MODEL)
    await db.commit()
    return ok(data)
