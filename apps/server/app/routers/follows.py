"""关注系统路由：关注/取关 + 粉丝/关注列表 + 关注动态 feed。

- 关注/取关挂在 `/api/users/{user_id}/follow`（与帖子点赞 `/posts/:id/like` 同构）
- 个人主页 `GET /api/users/{user_id}` 在 users.py
- 关注动态 `GET /api/follows/feed` 复用 posts.py 的 `_post_out` 序列化
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.follow import Follow
from app.models.post import Post
from app.models.user import User
from app.routers.posts import _post_out

users_router = APIRouter(prefix="/users", tags=["follows"])
follows_router = APIRouter(prefix="/follows", tags=["follows"])


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("用户不存在", code=404, status_code=404)
    return user


def _user_summary(u: User, is_following: bool) -> dict:
    return {
        "id": str(u.id),
        "nickname": u.nickname if u.nickname else "美食猎人",
        "avatar_url": u.avatar_url,
        "follower_count": u.follower_count,
        "following_count": u.following_count,
        "is_following": is_following,
    }


async def _my_followed_ids(db: AsyncSession, user_id: UUID) -> set[UUID]:
    rows = await db.execute(select(Follow.following_id).where(Follow.follower_id == user_id))
    return {r[0] for r in rows.all()}


async def _fetch_users(db: AsyncSession, ids: list[UUID]) -> list[User]:
    if not ids:
        return []
    rows = await db.execute(select(User).where(User.id.in_(set(ids))))
    return list(rows.scalars())


async def _is_following(db: AsyncSession, follower_id: UUID, following_id: UUID) -> bool:
    row = await db.execute(
        select(Follow.id).where(Follow.follower_id == follower_id, Follow.following_id == following_id)
    )
    return row.scalar_one_or_none() is not None


# ---------- 关注 / 取关 ----------
@users_router.post("/{user_id}/follow")
async def follow_user(
    user_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """关注用户（幂等；禁自关注）。"""
    target = await _get_user_or_404(db, user_id)
    if target.id == user.id:
        raise AppError("不能关注自己", code=400, status_code=400)
    exists = await db.execute(
        select(Follow).where(Follow.follower_id == user.id, Follow.following_id == target.id)
    )
    if exists.scalar_one_or_none() is None:
        db.add(Follow(follower_id=user.id, following_id=target.id))
        user.following_count += 1
        target.follower_count += 1
        await db.commit()
        await db.refresh(user)
        await db.refresh(target)
    return ok(
        {
            "following": True,
            "follower_count": target.follower_count,
            "following_count": user.following_count,
        }
    )


@users_router.delete("/{user_id}/follow")
async def unfollow_user(
    user_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """取消关注（幂等；计数不小于 0）。"""
    target = await _get_user_or_404(db, user_id)
    exists = await db.execute(
        select(Follow).where(Follow.follower_id == user.id, Follow.following_id == target.id)
    )
    follow = exists.scalar_one_or_none()
    if follow is not None:
        await db.delete(follow)
        user.following_count = max(0, user.following_count - 1)
        target.follower_count = max(0, target.follower_count - 1)
        await db.commit()
        await db.refresh(user)
        await db.refresh(target)
    return ok(
        {
            "following": False,
            "follower_count": target.follower_count,
            "following_count": user.following_count,
        }
    )


# ---------- 粉丝 / 关注列表 ----------
@users_router.get("/{user_id}/followers")
async def list_followers(
    user_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """某用户的粉丝列表（谁关注了 TA）。"""
    target = await _get_user_or_404(db, user_id)
    total = (
        await db.execute(
            select(func.count()).select_from(Follow).where(Follow.following_id == target.id)
        )
    ).scalar_one()
    rows = await db.execute(
        select(Follow.follower_id)
        .where(Follow.following_id == target.id)
        .order_by(Follow.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    follower_ids = [r[0] for r in rows.all()]
    followers = await _fetch_users(db, follower_ids)
    followed_set = await _my_followed_ids(db, user.id)
    items = [_user_summary(u, u.id in followed_set) for u in followers]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )


@users_router.get("/{user_id}/following")
async def list_following(
    user_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """某用户的关注列表（TA 关注了谁）。"""
    target = await _get_user_or_404(db, user_id)
    total = (
        await db.execute(
            select(func.count()).select_from(Follow).where(Follow.follower_id == target.id)
        )
    ).scalar_one()
    rows = await db.execute(
        select(Follow.following_id)
        .where(Follow.follower_id == target.id)
        .order_by(Follow.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    following_ids = [r[0] for r in rows.all()]
    following = await _fetch_users(db, following_ids)
    followed_set = await _my_followed_ids(db, user.id)
    items = [_user_summary(u, u.id in followed_set) for u in following]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )


# ---------- 关注动态 feed ----------
@follows_router.get("/feed")
async def follow_feed(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """关注动态：我关注的人的最新作品，时间倒序分页。"""
    followed_ids = await _my_followed_ids(db, user.id)
    if not followed_ids:
        return ok({"items": [], "total": 0, "page": page, "size": size, "has_more": False})

    total = (
        await db.execute(
            select(func.count()).select_from(Post).where(Post.user_id.in_(followed_ids))
        )
    ).scalar_one()
    rows = await db.execute(
        select(Post)
        .where(Post.user_id.in_(followed_ids))
        .order_by(Post.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    posts = list(rows.scalars().all())

    authors = {u.id: u for u in await _fetch_users(db, [p.user_id for p in posts])}
    liked_ids: set[UUID] = set()
    if posts:
        from app.models.like import Like

        liked_rows = await db.execute(
            select(Like.post_id).where(Like.user_id == user.id, Like.post_id.in_([p.id for p in posts]))
        )
        liked_ids = {r[0] for r in liked_rows.all()}

    items = [_post_out(p, authors.get(p.user_id), p.id in liked_ids, followed_ids) for p in posts]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "has_more": page * size < total,
        }
    )
