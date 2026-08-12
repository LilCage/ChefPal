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
from app.models.recipe_kb import RecipeKB
from app.models.user import User
from app.services import taste_memory as taste_service

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteCreate(BaseModel):
    content_type: Literal["qa", "recipe", "kb"]
    content_id: UUID


async def _ensure_content_owned(
    db: AsyncSession, user_id: UUID, content_type: str, content_id: UUID
) -> None:
    """校验收藏对象存在且属于当前用户（问答/菜谱需归属本人；知识库为公共菜谱仅查存在）。"""
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
    elif content_type == "kb":
        row = await db.execute(select(RecipeKB).where(RecipeKB.id == content_id))
        if row.scalar_one_or_none() is None:
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
        # AI 口味记忆埋点：收藏菜谱记 style，收藏问答记 question 关键词（EXT-13.1）
        await _record_taste_signal(db, user.id, body.content_type, body.content_id)
        await db.commit()
        await db.refresh(fav)
    return ok(_fav_item(fav))


async def _record_taste_signal(
    db: AsyncSession, user_id: UUID, content_type: str, content_id: UUID
) -> None:
    """收藏时记录口味信号：菜谱→style，问答→question 前 5 个词。失败静默（不影响主流程）。"""
    try:
        if content_type == "recipe":
            row = await db.execute(select(Recipe).where(Recipe.id == content_id))
            rec = row.scalar_one_or_none()
            if rec and rec.style:
                await taste_service.record_signal(db, user_id, "favorite_recipe", rec.style)
        elif content_type == "kb":
            row = await db.execute(select(RecipeKB).where(RecipeKB.id == content_id))
            rec = row.scalar_one_or_none()
            if rec:
                # 知识库菜谱：优先风味标签，其次菜名关键词
                signal = rec.style or rec.title[:20]
                await taste_service.record_signal(db, user_id, "favorite_recipe", signal)
        elif content_type == "qa":
            row = await db.execute(select(QA_Record).where(QA_Record.id == content_id))
            rec = row.scalar_one_or_none()
            if rec:
                # 取 question 前 20 字作为关键词信号
                await taste_service.record_signal(db, user_id, "favorite_qa", rec.question[:20])
    except Exception:  # noqa: BLE001 埋点失败不影响收藏
        pass


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
    """批量取回问答/菜谱/知识库内容，组装收藏列表。"""
    qa_ids = [f.content_id for f in favs if f.content_type == "qa"]
    rec_ids = [f.content_id for f in favs if f.content_type == "recipe"]
    kb_ids = [f.content_id for f in favs if f.content_type == "kb"]

    qa_map: dict[UUID, QA_Record] = {}
    if qa_ids:
        rows = await db.execute(select(QA_Record).where(QA_Record.id.in_(qa_ids)))
        qa_map = {r.id: r for r in rows.scalars()}
    rec_map: dict[UUID, Recipe] = {}
    if rec_ids:
        rows = await db.execute(select(Recipe).where(Recipe.id.in_(rec_ids)))
        rec_map = {r.id: r for r in rows.scalars()}
    kb_map: dict[UUID, RecipeKB] = {}
    if kb_ids:
        rows = await db.execute(select(RecipeKB).where(RecipeKB.id.in_(kb_ids)))
        kb_map = {r.id: r for r in rows.scalars()}

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
        elif fav.content_type == "kb":
            rec = kb_map.get(fav.content_id)
            content = (
                {
                    "title": rec.title,
                    "style": rec.style,
                    "time_minutes": rec.time_minutes,
                    "difficulty": rec.difficulty,
                    "hit_count": rec.hit_count,
                    "summary": rec.summary,
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
    type: Literal["qa", "recipe", "kb"] | None = Query(default=None, alias="type"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """收藏列表，可按 ?type=qa|recipe|kb 过滤。"""
    query = select(Favorite).where(Favorite.user_id == user.id)
    if type:
        query = query.where(Favorite.content_type == type)
    query = query.order_by(Favorite.created_at.desc())
    rows = await db.execute(query)
    favs = rows.scalars().all()
    items = await _enrich(db, list(favs))
    return ok(items)
