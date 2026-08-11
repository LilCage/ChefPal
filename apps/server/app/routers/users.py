"""用户路由：GET /api/users/me、PUT /api/users/me/profile、PUT /api/users/me/preferences、DELETE /api/users/me、GET /api/users/{id}（作者主页）。"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import AppError, ok
from app.db.session import get_db
from app.models.follow import Follow
from app.models.post import Post
from app.models.user import User
from app.schemas.api import PreferencesUpdate, ProfileUpdate, UserOut
from app.services import taste_memory as taste_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """当前用户信息。"""
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.put("/me/profile")
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """编辑个人资料（昵称/头像），仅合并传入字段。"""
    if body.nickname is not None:
        nickname = body.nickname.strip()
        user.nickname = nickname or None
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url or None
    await db.commit()
    await db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.delete("/me")
async def delete_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """注销账号：删除当前用户，级联清理其收藏/问答/菜谱/AI 调用流水。"""
    await db.delete(user)
    await db.commit()
    return ok(message="账号已注销")


@router.get("/me/taste-memory")
async def get_taste_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI 口味记忆（EXT-13.1）：查看聚合出的口味画像。"""
    profile = await taste_service.summarize_taste(db, user.id)
    return ok(profile)


@router.delete("/me/taste-memory")
async def clear_taste_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """清空 AI 口味记忆（用户可随时重置，不再注入历史偏好）。"""
    deleted = await taste_service.clear_signals(db, user.id)
    await db.commit()
    return ok({"deleted": deleted, "message": "口味记忆已清空"})


@router.put("/me/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """口味偏好设置（忌口/辣度/咸淡/技能），JSONB 存 users.preferences。"""
    # 仅合并传入的字段，保留未涉及的历史偏好
    prefs = dict(user.preferences or {})
    updates = body.model_dump(exclude_unset=True)
    prefs.update(updates)
    user.preferences = prefs
    await db.commit()
    await db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


# ---------- 作者主页（注意：/me 系列需在 /{user_id} 之前注册）----------
@router.get("/{user_id}")
async def get_user_profile(
    user_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """作者主页：档案 + 关注/粉丝/作品计数 + 我是否已关注 TA。"""
    target = await db.get(User, user_id)
    if target is None:
        raise AppError("用户不存在", code=404, status_code=404)

    row = await db.execute(
        select(Follow.id).where(Follow.follower_id == user.id, Follow.following_id == target.id)
    )
    is_following = row.scalar_one_or_none() is not None
    post_count = (
        await db.execute(select(func.count()).select_from(Post).where(Post.user_id == target.id))
    ).scalar_one()

    return ok(
        {
            "id": str(target.id),
            "nickname": target.nickname if target.nickname else "美食猎人",
            "avatar_url": target.avatar_url,
            "follower_count": target.follower_count,
            "following_count": target.following_count,
            "post_count": post_count,
            "is_following": is_following,
        }
    )
