"""一次性回填：给历史 QA 记录的 answer 补齐 kb_id（此前 flush 后原地 dict 修改丢失导致 kb_id=None）。

只为已收录到 recipe_kb 的菜/做法回填：dish_name 与每条 recommendation 按 (kind=recipe, title) 精确查库。
修复后前端"收藏某道菜"与"查看完整菜谱"可用 id 直达，无需再走 title 兜底。

用法：cd apps/server && .venv/Scripts/python.exe scripts/backfill_qa_kb_id.py
"""
import asyncio
import json

import asyncpg

DATABASE_URL = "postgresql://chefpal:chefpal_dev_password@localhost:5432/chefpal"


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)

    # 预取全部菜名 → id 映射（recipe 类，标题可能重复 → 取最新一条）
    kb_rows = await conn.fetch(
        "SELECT id, title FROM recipe_kb WHERE kind='recipe' ORDER BY created_at DESC"
    )
    id_by_title: dict[str, str] = {}
    for row in kb_rows:
        id_by_title.setdefault(row["title"], str(row["id"]))

    records = await conn.fetch(
        "SELECT id, answer FROM qa_records WHERE answer ? 'recommendations' OR answer ? 'dish_name'"
    )
    updated = 0
    for rec in records:
        answer = json.loads(rec["answer"])
        changed = False

        dish = answer.get("dish_name")
        if dish and not answer.get("kb_id"):
            kb_id = id_by_title.get(dish)
            if kb_id:
                answer["kb_id"] = kb_id
                changed = True

        for r in answer.get("recommendations") or []:
            name = (r or {}).get("name")
            if name and not r.get("kb_id"):
                kb_id = id_by_title.get(name)
                if kb_id:
                    r["kb_id"] = kb_id
                    changed = True

        if changed:
            await conn.execute(
                "UPDATE qa_records SET answer=$1::jsonb WHERE id=$2", json.dumps(answer), rec["id"]
            )
            updated += 1

    print(f"已回填 {updated} 条 QA 记录的 kb_id")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
