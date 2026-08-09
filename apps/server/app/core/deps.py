"""FastAPI 依赖：数据库会话与当前用户鉴权。"""
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <JWT> 解析当前用户，非法则 401。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("未登录", code=401, status_code=401)
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise AppError("登录态已过期，请重新登录", code=401, status_code=401)
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError("用户不存在", code=401, status_code=401)
    return user
