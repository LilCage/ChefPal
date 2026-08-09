"""社区作品表：文字心得 + 图片 + 可选关联菜谱/话题 + 冗余点赞计数。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 文字心得
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 图片公网 URL 数组（COS 或本地 /static）
    images: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 关联原 AI 菜谱（可空；菜谱删除时置空）
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    # 话题标签（基础版单选，如 "#今日晚餐"）
    topic: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    # 冗余点赞计数（LIKES 表幂等保障）
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
