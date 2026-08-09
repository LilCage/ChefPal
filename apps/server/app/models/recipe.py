"""AI 生成的菜谱表。JSONB 存结构化字段，raw_prompt 存 Prompt 快照可回溯。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    # [{ name, is_have, is_missing }]
    ingredients: Mapped[list] = mapped_column(JSONType, nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="简单")
    # [{ title, detail }]
    steps: Mapped[list] = mapped_column(JSONType, nullable=False)
    tips: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 缺什么调料（P1 展示）
    missing_seasonings: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    raw_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
