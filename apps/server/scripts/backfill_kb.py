"""把已有 AI 生成菜谱（recipes）与问答（qa_records）回填进菜谱知识库。

幂等：按 (kind, title) 去重，重复执行只更新不新增。
用法（apps/server 下）：
    .venv/Scripts/python scripts/backfill_kb.py
"""
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.qa_record import QA_Record
from app.models.recipe import Recipe
from app.services import kb as kb_service
from app.services.llm.embedding import aembed_texts

BATCH = 10


def _recipe_steps_to_text(steps: list) -> list[str]:
    out = []
    for s in steps or []:
        title = s.get("title", "") if isinstance(s, dict) else ""
        detail = s.get("detail", "") if isinstance(s, dict) else str(s)
        if title and detail:
            out.append(f"{title}：{detail}")
        elif detail:
            out.append(detail)
        elif title:
            out.append(title)
    return out


async def _collect(db) -> list[dict]:
    """收集待入库条目（不含向量）。"""
    entries: list[dict] = []

    # 1. AI 生成菜谱
    recipes = (await db.execute(select(Recipe))).scalars().all()
    for r in recipes:
        entries.append(
            {
                "kind": "recipe",
                "title": r.title,
                "summary": (r.tips[0] if r.tips else "") or "",
                "content": "",
                "ingredients": [i.get("name", "") for i in (r.ingredients or []) if i.get("name")],
                "steps": _recipe_steps_to_text(r.steps),
                "tips": r.tips or [],
                "time_minutes": r.time_minutes,
                "difficulty": r.difficulty,
                "style": r.style,
                "category": "",
                "source_type": kb_service.SOURCE_AI_RECIPE,
                "source_id": str(r.id),
            }
        )

    # 2. 问答结果（单菜做法 / 多菜推荐）
    records = (await db.execute(select(QA_Record))).scalars().all()
    for rec in records:
        answer = rec.answer or {}
        if answer.get("dish_name"):
            entries.append(
                {
                    "kind": "recipe",
                    "title": answer["dish_name"],
                    "summary": answer.get("core_secret", ""),
                    "content": "",
                    "ingredients": answer.get("ingredients", []),
                    "steps": answer.get("steps", []),
                    "tips": answer.get("avoid_pitfalls", []),
                    "time_minutes": 0,
                    "difficulty": "简单",
                    "style": "",
                    "category": "",
                    "source_type": kb_service.SOURCE_QA_ANSWER,
                    "source_id": str(rec.id),
                }
            )
        for r in (answer.get("recommendations") or []):
            name = (r or {}).get("name")
            if not name:
                continue
            entries.append(
                {
                    "kind": "recipe",
                    "title": name,
                    "summary": r.get("core_secret", ""),
                    "content": "",
                    "ingredients": r.get("ingredients", []),
                    "steps": [],
                    "tips": [],
                    "time_minutes": r.get("time_minutes", 0),
                    "difficulty": "简单",
                    "style": "",
                    "category": "",
                    "source_type": kb_service.SOURCE_QA_ANSWER,
                    "source_id": str(rec.id),
                }
            )
    return entries


async def main() -> None:
    settings = get_settings()
    if not settings.DASHSCOPE_API_KEY:
        print("请先在 .env 填入 DASHSCOPE_API_KEY")
        return

    async with AsyncSessionLocal() as db:
        entries = await _collect(db)
    print(f"收集 {len(entries)} 条待回填条目")

    texts = [kb_service.build_embedding_text(e) for e in entries]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i : i + BATCH]
        try:
            vectors.extend(await aembed_texts(chunk, input_type="document"))
        except Exception as exc:  # noqa: BLE001
            print(f"第 {i} 批向量化失败: {exc}")
            vectors.extend([None] * len(chunk))
        print(f"  向量化 {len(vectors)}/{len(texts)}")

    async with AsyncSessionLocal() as db:
        ok = 0
        for entry, emb in zip(entries, vectors):
            if emb is None:
                continue
            await kb_service.upsert_kb_entry(db, **entry, embedding=emb)
            ok += 1
        await db.commit()
        print(f"回填完成：{ok} 成功")


if __name__ == "__main__":
    asyncio.run(main())
