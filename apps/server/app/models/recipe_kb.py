"""菜谱知识库表（recipe_kb）：HowToCook 种子 + AI 生成沉淀，pgvector 向量检索。

统一承载两类知识条目：
- kind="recipe"：一道菜（title=菜名，ingredients/steps/tips 结构化）
- kind="tip"：厨房技巧/指南（title=技巧名，content=全文，ingredients/steps 为空）
embedding 由百炼 text-embedding-v3 计算（1024 维）。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import JSONType, VectorType

settings = get_settings()


class RecipeKB(Base):
    __tablename__ = "recipe_kb"
    __table_args__ = (
        Index("ix_kb_kind_title", "kind", "title"),
        Index("ix_kb_source", "source_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # recipe | tip
    title: Mapped[str] = mapped_column(String(128), nullable=False)  # 菜名 / 技巧名
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 简介/核心秘诀
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")  # tip 全文；recipe 可空
    # 食材清单（recipe 用，list[str]）
    ingredients: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 全量步骤（recipe 用，list[str] 编号文本；prep + cook 合并，兼容旧消费方）
    steps: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 食材处理步骤（切/洗/腌/焯等）
    prep_steps: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 烹饪步骤（下锅/调味/出锅等）
    cook_steps: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 成品图（仓库内相对路径列表，如 dishes/xxx/1.jpeg）
    images: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # 附加技巧/避坑（recipe 用，list[str]）
    tips: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="简单")
    style: Mapped[str] = mapped_column(String(16), nullable=False, default="")  # 风味标签
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="")  # 分类（素菜/肉菜/技巧…）
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # howtocook | ai_recipe | qa_answer | my_recipe
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")  # HowToCook 路径 / 源记录 id
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float]] = mapped_column(
        VectorType(settings.EMBEDDING_DIM), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
