"""用户表。MVP 阶段仅依赖 openid 匿名即可跑通闭环。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid, func
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
    # 忌口/辣度/咸淡/技能 + onboarded（新用户引导是否已看过），JSONB 注入菜谱 Agent
    preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    # 冗余关注/粉丝计数（follows 表幂等保障，对齐 like_count/comment_count 模式）
    follower_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def onboarded(self) -> bool:
        """是否已看过新用户引导（存 preferences，随账号走，不怕本地缓存被清）。"""
        return bool((self.preferences or {}).get("onboarded", False))
