"""挑战参与者表：一用户一挑战一条记录，记录花费与完成餐数（排行榜依据）。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChallengeParticipant(Base):
    __tablename__ = "challenge_participants"
    __table_args__ = (UniqueConstraint("challenge_id", "user_id", name="uq_challenge_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    spend: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 已花费（元）
    meal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 已完成餐数
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
