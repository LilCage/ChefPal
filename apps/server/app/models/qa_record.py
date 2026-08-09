"""AI 问答记录表。answer 为结构化 QASchema 的 JSONB 落库。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class QA_Record(Base):
    __tablename__ = "qa_records"
    __table_args__ = (
        # 用户+时间 联合索引，支撑"最近 N 条"查询
        Index("ix_qa_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # 结构化: { core_secret, ingredients[], steps[], avoid_pitfalls[], sources[] }
    answer: Mapped[dict] = mapped_column(JSONType, nullable=False)
    sources: Mapped[list | None] = mapped_column(JSONType, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
