"""真实 AI 冒烟：验证 7 天膳食规划 + 营养分析 Agent（直接调 planner_agent，不经 HTTP）。

运行：.venv/Scripts/python scripts/smoke_7day_plan.py
注意：消耗 1 次真实 AI 调用。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.ai import MealPlanSchema
from app.services.agents import planner_agent


async def main() -> None:
    print("== 7 天膳食规划冒烟（真实 AI）==")
    prefs = {"allergies": ["花生"], "spiciness": 2, "saltiness": "偏淡", "skill": "厨房小白"}
    out = await planner_agent.run_planner(prefs, days=7)
    if out["error"] or out["result"] is None:
        print(f"✗ 失败: {out['error']}")
        sys.exit(1)
    parsed = MealPlanSchema.model_validate(out["result"])
    days = parsed.days
    print(f"✓ 生成 {len(days)} 天")
    for d in days:
        print(f"  {d.day_label}: {d.total_kcal}千卡 蛋白{d.protein_g}g 脂{d.fat_g}g 碳水{d.carbs_g}g "
              f"| 3餐={'✓' if len(d.meals)==3 else '✗'}")
    if len(days) != 7 or not all(len(d.meals) == 3 for d in days):
        print("✗ 天数/餐数不符")
        sys.exit(1)
    print("== 7 天规划冒烟通过 ==")


if __name__ == "__main__":
    asyncio.run(main())
