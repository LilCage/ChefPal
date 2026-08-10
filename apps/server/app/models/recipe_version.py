"""菜谱版本表（菜谱DNA进化树，原型 05 屏6）：记录菜谱的修改轨迹。

- 根版本（v1.0 原版）在首次 fork 时懒创建（parent_id=None）
- 后续 fork 生成子版本（v2.0、v3.0...），parent_id 指向上一版本
- version_label 按链上顺序递增，供前端进化树时间线渲染
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecipeVersion(Base):
    __tablename__ = "recipe_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 所属菜谱（DNA 源头）
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    # 上一版本（根为 None）
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recipe_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 修改者
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(16), nullable=False)  # v1.0 / v2.0 ...
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    changes: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 这一版改了什么
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
