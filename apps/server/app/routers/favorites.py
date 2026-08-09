"""收藏路由：POST/DELETE/GET /api/favorites（content_type + content_id 多态）。"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.favorite import Favorite
from app.models.qa_record import QA_Record
from app.models.recipe import Recipe
from app.models.user import User

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteCreate(BaseModel):
    content_type: Literal["qa", "recipe"]
    content_id: UUID


async def _ensure_content_owned(
    db: AsyncSession, user_id: UUID, content_type: str, content_id: UUID
) -> None:
    """校验收藏对象存在且属于当前用户（只能收藏自己的问答/菜谱）。"""
    if content_type == "qa":
        row = await db.execute(select(QA_Record).where(QA_Record.id == content_id))
        rec = row.scalar_one_or_none()
        if rec is None or rec.user_id != user_id:
            raise AppError("内容不存在", code=404, status_code=404)
    elif content_type == "recipe":
        row = await db.execute(select(Recipe).where(Recipe.id == content_id))
        rec = row.scalar_one_or_none()
        if rec is None or rec.user_id != user_id:
            raise AppError("内容不存在", code=404, status_code=404)


def _fav_item(fav: Favorite, content: dict | None = None) -> dict:
    return {
        "favorite_id": str(fav.id),
        "content_type": fav.content_type,
        "content_id": str(fav.content_id),
        "content": content,
        "created_at": fav.created_at.isoformat() if fav.created_at else None,
    }


@router.post("")
async def add_favorite(
    body: FavoriteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """收藏（幂等：重复收藏返回已存在）。"""
    await _ensure_content_owned(db, user.id, body.content_type, body.content_id)
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.content_type == body.content_type,
            Favorite.content_id == body.content_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if fav is None:
        fav = Favorite(user_id=user.id, content_type=body.content_type, content_id=body.content_id)
        db.add(fav)
        await db.commit()
        await db.refresh(fav)
    return ok(_fav_item(fav))


@router.delete("")
async def remove_favorite(
    content_type: Literal["qa", "recipe"] = Query(...),
    content_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """取消收藏（幂等）。"""
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.content_type == content_type,
            Favorite.content_id == content_id,
        )
    )
    fav = existing.scalar_one_or_none()
    if fav is not None:
        await db.delete(fav)
        await db.commit()
    return ok(message="已取消收藏")


async def _enrich(db: AsyncSession, favs: list[Favorite]) -> list[dict]:
    """批量取回问答/菜谱内容，组装收藏列表。"""
    qa_ids = [f.content_id for f in favs if f.content_type == "qa"]
    rec_ids = [f.content_id for f in favs if f.content_type == "recipe"]

    qa_map: dict[UUID, QA_Record] = {}
    if qa_ids:
        rows = await db.execute(select(QA_Record).where(QA_Record.id.in_(qa_ids)))
        qa_map = {r.id: r for r in rows.scalars()}
    rec_map: dict[UUID, Recipe] = {}
    if rec_ids:
        rows = await db.execute(select(Recipe).where(Recipe.id.in_(rec_ids)))
        rec_map = {r.id: r for r in rows.scalars()}

    items = []
    for fav in favs:
        if fav.content_type == "qa":
            rec = qa_map.get(fav.content_id)
            content = (
                {
                    "question": rec.question,
                    "core_secret": rec.answer.get("core_secret"),
                    "created_at": rec.created_at.isoformat() if rec.created_at else None,
                }
                if rec
                else None
            )
        else:
            rec = rec_map.get(fav.content_id)
            content = (
                {
                    "title": rec.title,
                    "match_score": rec.match_score,
                    "time_minutes": rec.time_minutes,
                    "difficulty": rec.difficulty,
                    "steps": rec.steps,
                    "tips": rec.tips,
                }
                if rec
                else None
            )
        items.append(_fav_item(fav, content))
    return items


@router.get("")
async def list_favorites(
    type: Literal["qa", "recipe"] | None = Query(default=None, alias="type"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """收藏列表，可按 ?type=qa|recipe 过滤。"""
    query = select(Favorite).where(Favorite.user_id == user.id)
    if type:
        query = query.where(Favorite.content_type == type)
    query = query.order_by(Favorite.created_at.desc())
    rows = await db.execute(query)
    favs = rows.scalars().all()
    items = await _enrich(db, list(favs))
    return ok(items)
