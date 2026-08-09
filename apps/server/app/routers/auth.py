"""认证路由：POST /api/auth/login（code → JWT + 用户）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import AppError, ok
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.api import LoginRequest, UserOut
from app.services import wechat as wechat_service
from app.services.wechat import WeChatError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """微信一键登录：code 换 openid，查/建用户，签发 JWT。"""
    try:
        session = await wechat_service.code2session(body.code)
    except WeChatError as exc:
        raise AppError(f"微信登录失败：{exc}", code=401, status_code=401)

    openid = session.get("openid")
    if not openid:
        raise AppError("微信登录失败：未获取到 openid", code=401, status_code=401)

    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(openid=openid)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token(str(user.id))
    return ok(
        {
            "token": token,
            "user": UserOut.model_validate(user).model_dump(mode="json"),
        }
    )
