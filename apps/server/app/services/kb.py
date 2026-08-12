"""菜谱知识库服务：条目 upsert（按 kind+title 去重）+ pgvector 向量检索。

数据来源：
- HowToCook 种子（scripts/import_howtocook.py 灌入）
- AI 生成菜谱 / 问答沉淀（qa 集成自动入库）
- 已有 AI 菜谱 / 问答回填（scripts/backfill_kb.py）
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.recipe_kb import RecipeKB
from app.services.llm.embedding import EmbeddingError, aembed_texts

settings = get_settings()

SOURCE_HOWTOCOOK = "howtocook"
SOURCE_AI_RECIPE = "ai_recipe"
SOURCE_QA_ANSWER = "qa_answer"
SOURCE_MY_RECIPE = "my_recipe"

# 知识库条目可接受的字段（与 RecipeKB 列对应）
_ENTRY_FIELDS = (
    "kind",
    "title",
    "summary",
    "content",
    "ingredients",
    "steps",
    "prep_steps",
    "cook_steps",
    "images",
    "tips",
    "time_minutes",
    "difficulty",
    "style",
    "category",
    "source_type",
    "source_id",
)


def build_embedding_text(entry: dict) -> str:
    """构造用于向量化的文本：菜名 + 简介 + 食材 + 步骤 + 技巧（tip 则用全文）。"""
    parts = [entry.get("title") or ""]
    if entry.get("summary"):
        parts.append(entry["summary"])
    ings = entry.get("ingredients") or []
    if ings:
        parts.append("食材：" + "、".join(ings))
    steps = entry.get("steps") or []
    if not steps and (entry.get("prep_steps") or entry.get("cook_steps")):
        steps = (entry.get("prep_steps") or []) + (entry.get("cook_steps") or [])
    if steps:
        parts.append("步骤：" + " ".join(steps))
    tips = entry.get("tips") or []
    if tips:
        parts.append("技巧：" + " ".join(tips))
    if entry.get("content"):
        parts.append(entry["content"])
    return "\n".join(p for p in parts if p)


async def upsert_kb_entry(
    db: AsyncSession,
    *,
    kind: str,
    title: str,
    summary: str = "",
    content: str = "",
    ingredients: list[str] | None = None,
    steps: list[str] | None = None,
    prep_steps: list[str] | None = None,
    cook_steps: list[str] | None = None,
    images: list[str] | None = None,
    tips: list[str] | None = None,
    time_minutes: int = 0,
    difficulty: str = "简单",
    style: str = "",
    category: str = "",
    source_type: str,
    source_id: str = "",
    embedding: list[float] | None = None,
) -> RecipeKB:
    """按 (kind, title) 去重 upsert：已存在则更新内容与向量，否则新建。

    embedding 未提供时自动调用 aembed_texts 计算（失败抛 EmbeddingError）；
    批量导入可预计算向量后传入，避免逐条调用。
    """
    data = {
        "kind": kind,
        "title": title,
        "summary": summary,
        "content": content,
        "ingredients": ingredients or [],
        "steps": steps or [],
        "prep_steps": prep_steps or [],
        "cook_steps": cook_steps or [],
        "images": images or [],
        "tips": tips or [],
        "time_minutes": time_minutes,
        "difficulty": difficulty,
        "style": style,
        "category": category,
        "source_type": source_type,
        "source_id": source_id,
    }
    if embedding is None:
        text = build_embedding_text(data)
        emb = (await aembed_texts([text], input_type="document"))[0]
    else:
        emb = embedding

    result = await db.execute(
        select(RecipeKB).where(RecipeKB.kind == kind, RecipeKB.title == title)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # HowToCook 为权威种子：非 HowToCook 来源（AI 生成/问答回填）不得覆盖它
        if existing.source_type == SOURCE_HOWTOCOOK and data["source_type"] != SOURCE_HOWTOCOOK:
            return existing
        for key in _ENTRY_FIELDS:
            setattr(existing, key, data[key])
        existing.embedding = emb
        db.add(existing)
        return existing

    entry = RecipeKB(**data, embedding=emb)
    db.add(entry)
    await db.flush()
    return entry


async def search_kb(
    db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
    min_similarity: float | None = None,
    kinds: list[str] | None = None,
) -> list[dict]:
    """向量检索：embed 问题 → 按 cosine 距离排序 → 阈值过滤。

    返回 [{entry: RecipeKB, similarity: float}, ...] 按相似度降序。
    """
    top_k = top_k or settings.KB_TOP_K
    min_similarity = settings.KB_MIN_SIMILARITY if min_similarity is None else min_similarity
    qvec = (await aembed_texts([query], input_type="query"))[0]

    stmt = (
        select(RecipeKB, RecipeKB.embedding.cosine_distance(qvec).label("dist"))
        .order_by(RecipeKB.embedding.cosine_distance(qvec))
        .limit(top_k * 3)
    )
    if kinds:
        stmt = stmt.where(RecipeKB.kind.in_(kinds))
    result = await db.execute(stmt)
    rows = result.all()

    hits: list[dict] = []
    for entry, dist in rows:
        sim = 1.0 - float(dist)
        if sim >= min_similarity:
            hits.append({"entry": entry, "similarity": sim})
    hits.sort(key=lambda h: h["similarity"], reverse=True)
    return hits[:top_k]


async def get_kb_entry(db: AsyncSession, entry_id: uuid.UUID) -> RecipeKB | None:
    result = await db.execute(select(RecipeKB).where(RecipeKB.id == entry_id))
    return result.scalar_one_or_none()


async def get_kb_entry_by_title(
    db: AsyncSession, title: str, *, kind: str = "recipe"
) -> RecipeKB | None:
    """精确菜名查库（多菜推荐点详情用；先按原文，再尝试去掉做法后缀）。"""
    result = await db.execute(
        select(RecipeKB).where(RecipeKB.kind == kind, func.lower(RecipeKB.title) == func.lower(title))
    )
    entry = result.scalar_one_or_none()
    if entry is not None:
        return entry
    # 兜底：去掉"的做法/菜谱"后缀再查
    for suffix in ("的做法", "菜谱", "做法"):
        if title.endswith(suffix):
            core = title[: -len(suffix)]
            result = await db.execute(
                select(RecipeKB).where(RecipeKB.kind == kind, func.lower(RecipeKB.title) == func.lower(core))
            )
            entry = result.scalar_one_or_none()
            if entry is not None:
                return entry
    return None


async def increment_hit(db: AsyncSession, entry: RecipeKB) -> None:
    """命中计数 +1（幂等写，用于统计热门知识）。"""
    entry.hit_count = entry.hit_count + 1
    await db.flush()


async def store_generated_answer_to_kb(
    db: AsyncSession, answer: dict, record_id: uuid.UUID
) -> None:
    """把 AI/解析生成的单菜或多菜结果按菜名入库（best-effort，embedding 失败静默）。

    qa 问答、parse 链接/文档解析共用：生成结果沉淀为知识库条目，
    HowToCook 权威条目不被覆盖（upsert 内已判 source_type）。
    入库成功后把生成的 entry id 回填到 answer（dish_name → answer["kb_id"]，
    recommendations → 每项 r["kb_id"]），供前端"查看完整菜谱/收藏"跳转与收藏。
    """
    try:
        if answer.get("dish_name"):
            entry = await upsert_kb_entry(
                db,
                kind="recipe",
                title=answer["dish_name"],
                summary=answer.get("core_secret", ""),
                ingredients=answer.get("ingredients", []),
                steps=answer.get("steps", []),
                prep_steps=answer.get("prep_steps", []),
                cook_steps=answer.get("cook_steps", []),
                tips=answer.get("avoid_pitfalls", []),
                source_type=SOURCE_QA_ANSWER,
                source_id=str(record_id),
            )
            if entry is not None:
                answer["kb_id"] = str(entry.id)
        for r in (answer.get("recommendations") or []):
            name = (r or {}).get("name")
            if not name:
                continue
            entry = await upsert_kb_entry(
                db,
                kind="recipe",
                title=name,
                summary=r.get("core_secret", ""),
                ingredients=r.get("ingredients", []),
                source_type=SOURCE_QA_ANSWER,
                source_id=str(record_id),
            )
            if entry is not None:
                r["kb_id"] = str(entry.id)
        await db.flush()
    except EmbeddingError:
        pass  # 知识库不可用不影响主流程


def to_kb_out(entry: RecipeKB, *, similarity: float | None = None) -> dict:
    """序列化为 API 输出（对齐前端渲染字段）。"""
    return {
        "id": str(entry.id),
        "kind": entry.kind,
        "title": entry.title,
        "summary": entry.summary,
        "content": entry.content,
        "ingredients": entry.ingredients,
        "steps": entry.steps,
        "prep_steps": entry.prep_steps,
        "cook_steps": entry.cook_steps,
        "images": entry.images,
        "tips": entry.tips,
        "time_minutes": entry.time_minutes,
        "difficulty": entry.difficulty,
        "style": entry.style,
        "category": entry.category,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "hit_count": entry.hit_count,
        "similarity": round(similarity, 4) if similarity is not None else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }
