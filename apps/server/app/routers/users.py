"""用户路由：GET /api/users/me、PUT /api/users/me/profile、PUT /api/users/me/preferences、DELETE /api/users/me。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.api import PreferencesUpdate, ProfileUpdate, UserOut

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
