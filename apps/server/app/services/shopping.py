"""购物清单生成：从膳食计划汇总各餐菜品 → AI 输出分类购物清单（含数量）。

校验失败重试 ≤AI_MAX_RETRIES，仍失败抛 ShoppingError。
"""
from app.core.config import get_settings
from app.schemas.ai import ShoppingListSchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

SHOPPING_SYSTEM = """你是采购清单生成助手。基于给定的 3 天膳食计划，汇总去重生成一份分类购物清单。
只输出 JSON，不要多余文字。JSON 结构：
{
  "categories": [
    {"name": "蔬菜水果", "items": [{"name": "西红柿", "quantity": "2 个"}, {"name": "西兰花", "quantity": "1 颗"}]},
    {"name": "蛋奶肉禽", "items": [{"name": "鸡蛋", "quantity": "6 枚"}, {"name": "鸡胸肉", "quantity": "300g"}]},
    {"name": "调料辅料", "items": [{"name": "小葱", "quantity": "1 把"}, {"name": "生抽", "quantity": "1 瓶"}]}
  ]
}
要求：
- 覆盖计划中所有菜品需要的食材与调味料，合并同类项，数量给出合理估算（如 2 个 / 300g / 1 瓶）
- 按食材品类分组（蔬菜水果 / 蛋奶肉禽 / 水产海鲜 / 主食豆类 / 调料辅料）
- 每类至少 1 项；数量是估算，供参考
安全要求：输出为通用购物建议，不构成医疗/营养处方。"""


class ShoppingError(Exception):
    """购物清单生成失败。"""


def _collect_dishes(plan_data: dict) -> list[str]:
    """从 MealPlanSchema 数据中收集所有菜品名（去重保序）。"""
    dishes: list[str] = []
    seen: set[str] = set()
    for day in plan_data.get("days", []):
        for meal in day.get("meals", []):
            for dish in meal.get("dishes", []):
                name = dish.get("name", "").strip()
                if name and name not in seen:
                    seen.add(name)
                    dishes.append(name)
    return dishes


async def generate_shopping_list(plan_data: dict) -> dict:
    """基于膳食计划生成分类购物清单（ShoppingListSchema 字典）。"""
    dishes = _collect_dishes(plan_data)
    if not dishes:
        raise ShoppingError("膳食计划中没有菜品，无法生成购物清单")

    user_msg = "3 天膳食计划的菜品：\n" + "\n".join(f"- {d}" for d in dishes)

    last_error = None
    for attempt in range(settings.AI_MAX_RETRIES + 1):
        try:
            data = await ainvoke_json(
                model=settings.DEEPSEEK_MODEL,
                system=SHOPPING_SYSTEM,
                user=user_msg,
                enable_search=False,
            )
            parsed = ShoppingListSchema.model_validate(data)
            if len(parsed.categories) >= 1:
                return parsed.model_dump()
            last_error = "购物清单结构不完整"
        except (LLMError, Exception) as exc:  # noqa: BLE001
            last_error = str(exc)
    raise ShoppingError(last_error or "购物清单生成失败，请稍后重试")
