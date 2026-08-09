"""JWT 签发与校验。"""
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

settings = get_settings()


def create_access_token(user_id: str) -> str:
    """签发 JWT，sub 携带用户 UUID。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """校验 JWT，返回 user_id；非法/过期返回 None。"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        sub = payload.get("sub")
        return sub if sub else None
    except jwt.PyJWTError:
        return None
