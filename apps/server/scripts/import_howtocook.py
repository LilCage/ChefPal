"""解析 kb_data/howtocook 并把菜谱+技巧批量灌入 recipe_kb 知识库。

先运行 scripts/fetch_howtocook.py 拉取数据。幂等：按 (kind, title) 去重，重复执行只更新不新增。
用法（apps/server 下）：
    .venv/Scripts/python scripts/import_howtocook.py
"""
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.howtocook.parser import (
    classify_category,
    parse_dish_markdown,
    parse_tip_markdown,
)
from app.services.kb import SOURCE_HOWTOCOOK, build_embedding_text, upsert_kb_entry
from app.services.llm.embedding import aembed_texts

KB_DATA = Path(__file__).resolve().parent.parent / "kb_data" / "howtocook"
BATCH = 10  # 百炼 text-embedding-v3 单次批量上限（>10 报 InvalidParameter）


def _collect() -> list[dict]:
    """解析全部文件 → 结构化条目（不含向量）。"""
    entries: list[dict] = []
    for f in sorted(KB_DATA.rglob("*.md")):
        rel = f.relative_to(KB_DATA).as_posix()
        md = f.read_text(encoding="utf-8")
        category = classify_category(rel)
        if rel.startswith("dishes/"):
            if "template" in rel or f.name == "README.md":
                continue
            d = parse_dish_markdown(md, category=category, source_id=rel)
            entries.append(
                {
                    "kind": "recipe",
                    "title": d.title,
                    "summary": d.summary,
                    "content": "",
                    "ingredients": d.ingredients,
                    "steps": d.steps,
                    "prep_steps": d.prep_steps,
                    "cook_steps": d.cook_steps,
                    "tips": d.tips,
                    # 只保留本地真实存在的成品图（fetch 已下载），避免破图
                    "images": [p for p in d.images if (KB_DATA / p).is_file()],
                    "time_minutes": 0,
                    "difficulty": d.difficulty,
                    "style": "",
                    "category": d.category,
                    "source_type": SOURCE_HOWTOCOOK,
                    "source_id": rel,
                }
            )
        elif rel.startswith("tips/"):
            d = parse_tip_markdown(md, category=category, source_id=rel)
            entries.append(
                {
                    "kind": "tip",
                    "title": d.title,
                    "summary": "",
                    "content": d.content,
                    "ingredients": [],
                    "steps": [],
                    "tips": [],
                    "time_minutes": 0,
                    "difficulty": "简单",
                    "style": "",
                    "category": d.category,
                    "source_type": SOURCE_HOWTOCOOK,
                    "source_id": rel,
                }
            )
    return entries


async def main() -> None:
    settings = get_settings()
    if not settings.DASHSCOPE_API_KEY:
        print("请先在 .env 填入 DASHSCOPE_API_KEY（embedding 需要）")
        return

    entries = _collect()
    print(f"共解析 {len(entries)} 条（recipe + tip）")

    # 批量计算向量（按 build_embedding_text 拼接）
    texts = [build_embedding_text(e) for e in entries]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i : i + BATCH]
        try:
            vecs = await aembed_texts(chunk, input_type="document")
            vectors.extend(vecs)
            print(f"  向量化 {len(vectors)}/{len(texts)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  第 {i} 批向量化失败: {exc}；跳过该批")
            vectors.extend([None] * len(chunk))

    # upsert 入库（幂等，按 kind+title 去重）
    async with AsyncSessionLocal() as db:
        ok = skip = 0
        for entry, emb in zip(entries, vectors):
            if emb is None:
                skip += 1
                continue
            await upsert_kb_entry(db, **entry, embedding=emb)
            ok += 1
        await db.commit()
        print(f"入库完成：{ok} 成功，{skip} 跳过（向量计算失败）")


if __name__ == "__main__":
    asyncio.run(main())
