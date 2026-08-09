"""用户表。MVP 阶段仅依赖 openid 匿名即可跑通闭环。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64), default=None)
    # base64 头像（data:image/...），长度可变故用 Text
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    # 忌口/辣度/咸淡/技能，JSONB 注入菜谱 Agent
    preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
