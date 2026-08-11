"""个人菜谱创作表（EXT-4.1）：用户自建菜谱，含图文步骤，可发布到社区。

与 recipes（AI 生成菜谱）区分：这是用户主动创作的菜谱，标题/食材/步骤/避坑全由用户填写，
封面图可选（COS/本地），发布到社区时作为 posts 的 my_recipe_id 关联。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class MyRecipe(Base):
    __tablename__ = "my_recipes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    # 封面图 URL（COS 或本地 /static，可空）
    cover_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # [{ name, amount }] 食材清单（amount 如 2个 / 300g / 适量）
    ingredients: Mapped[list] = mapped_column(JSONType, nullable=False)
    # [{ title, detail }] 步骤列表
    steps: Mapped[list] = mapped_column(JSONType, nullable=False)
    # 避坑指南（字符串数组）
    tips: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 风味标签（浓香下饭/清爽快手/蒸煮清淡/香辣过瘾等，与 AI 菜谱对齐）
    style: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="简单")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
