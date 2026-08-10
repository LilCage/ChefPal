"""冰箱食材表：记录食材添加时间与保质期，供过期预警（冰箱管家）计算临期状态。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FridgeItem(Base):
    __tablename__ = "fridge_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=True, default="")
    # 添加（购买/放入）时间，用于计算"已放 N 天"
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 保质期（天），用于计算"还剩 N 天"；常见食材可静态推断，兜底 7 天
    best_before_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
