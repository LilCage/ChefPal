"""AI 口味记忆信号表（EXT-13.1）：记录用户对某类口味的显式/隐式偏好行为。

- favorite_recipe: 收藏 AI 菜谱 → value = 该菜谱的 style（风味标签，如 浓香下饭）
- like_post:      点赞社区作品 → value = 作品 topic（话题，如 #减脂餐）
- favorite_qa:    收藏问答 → value = 问答 question 的前若干关键词

聚合时按 signal_type 分组统计 top value，形成"口味画像"注入推荐 Prompt（EXT-13.2）。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TasteSignal(Base):
    __tablename__ = "taste_signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(24), nullable=False)  # favorite_recipe / like_post / favorite_qa
    value: Mapped[str] = mapped_column(String(64), nullable=False)        # style / topic / 关键词
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
