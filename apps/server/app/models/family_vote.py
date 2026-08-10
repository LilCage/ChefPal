"""家庭口味投票表：AI 生成 3 道菜选项 + 投票统计（原型 05 屏2）。

- options JSONB: [{name, count}]，count 为冗余票数（vote_records 表幂等保障）
- 同一用户重复投票 = 改票：先减旧选项票数，再加新选项
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class FamilyVote(Base):
    __tablename__ = "family_votes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 发起人（决定今晚吃什么的人）
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 参与投票的冰箱食材快照
    ingredients: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # [{name, count}] 选项及票数
    options: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active / closed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
