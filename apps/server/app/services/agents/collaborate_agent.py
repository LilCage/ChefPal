"""多智能体协作 Agent（原型 05 屏5）：营养师 + 大厨 + 采购 并行输出。

三个独立子 Agent 通过 asyncio.gather 并行调用（对应 LangGraph fan-out 并行语义），
各自用 Pydantic Schema 校验，最后合并为 CollaborateSchema。任一失败 → 整体失败降级。
"""
import asyncio
from typing import TypedDict

from app.core.config import get_settings
from app.schemas.ai import (
    ChefOut,
    CollaborateSchema,
    NutritionistOut,
    ShopperOut,
)
from app.services.agents.recipe_agent import build_prefs_text
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

NUTRITIONIST_SYSTEM = """你是注册营养师 Agent。基于用户冰箱现有食材与减脂/健康目标，给出今日营养建议。
只输出 JSON，不要多余文字。JSON 结构：
{
  "calories_kcal": 今日建议热量(千卡),
  "protein_g": 建议蛋白质(克),
  "advice": "搭配建议（一句话）",
  "avoided_allergens": ["已避开的忌口/过敏原"]
}
硬性要求：蛋白质优先；严格规避用户忌口/过敏原并列入 avoided_allergens。
安全要求：输出为通用营养建议，不构成医疗处方。"""

CHEF_SYSTEM = """你是资深大厨 Agent。基于用户冰箱现有食材，推荐 1 道可行性最高的菜，并给出核心技法与摆盘建议。
只输出 JSON，不要多余文字。JSON 结构：
{
  "dish_name": "推荐菜名",
  "technique": "核心烹饪技法（写给厨房小白，明确火候与关键步骤）",
  "plating": "摆盘/装盘建议（可空字符串）"
}
硬性要求：优先使用现有食材；严格规避忌口/过敏原。"""

SHOPPER_SYSTEM = """你是精打细算的采购 Agent。基于用户要做的菜/现有食材，给出省钱采购清单。
只输出 JSON，不要多余文字。JSON 结构：
{
  "categories": [
    {"name": "品类名（如 蛋奶肉禽/蔬菜水果/调料辅料）", "items": [{"name": "商品", "quantity": "如 300g / 2个 / 1瓶"}]}
  ],
  "tips": "省钱小贴士（一句话）"
}
硬性要求：不重复采购冰箱已有的食材；优先平价替代品。"""


class CollaborateState(TypedDict, total=False):
    ingredients: list[str]
    prefs: dict
    result: dict | None
    error: str | None


async def _run_nutritionist(ingredients_text: str, prefs_text: str) -> dict:
    data = await ainvoke_json(
        model=settings.DEEPSEEK_MODEL,
        system=NUTRITIONIST_SYSTEM,
        user=f"冰箱食材：{ingredients_text}。用户偏好：{prefs_text}。请给营养建议。",
        enable_search=False,
    )
    return NutritionistOut.model_validate(data).model_dump()


async def _run_chef(ingredients_text: str, prefs_text: str) -> dict:
    data = await ainvoke_json(
        model=settings.DEEPSEEK_MODEL,
        system=CHEF_SYSTEM,
        user=f"冰箱食材：{ingredients_text}。用户偏好：{prefs_text}。请推荐 1 道菜。",
        enable_search=False,
    )
    return ChefOut.model_validate(data).model_dump()


async def _run_shopper(ingredients_text: str) -> dict:
    data = await ainvoke_json(
        model=settings.DEEPSEEK_MODEL,
        system=SHOPPER_SYSTEM,
        user=f"冰箱现有食材：{ingredients_text}。请给出需要补买的采购清单。",
        enable_search=False,
    )
    return ShopperOut.model_validate(data).model_dump()


async def run_collaborate(ingredients: list[str], prefs: dict | None = None) -> dict:
    """并行运行三个子 Agent，返回 CollaborateSchema 字典。

    返回 {"result": dict | None, "error": str | None}。任一子 Agent 失败 → result=None。
    """
    ingredients_text = "、".join(ingredients)
    prefs_text = build_prefs_text(prefs or {})

    try:
        nutritionist, chef, shopper = await asyncio.gather(
            _run_nutritionist(ingredients_text, prefs_text),
            _run_chef(ingredients_text, prefs_text),
            _run_shopper(ingredients_text),
        )
    except (LLMError, Exception) as exc:  # noqa: BLE001
        return {"result": None, "error": str(exc) or "多智能体协作失败，请稍后重试"}

    try:
        result = CollaborateSchema(
            nutritionist=NutritionistOut(**nutritionist),
            chef=ChefOut(**chef),
            shopper=ShopperOut(**shopper),
        ).model_dump()
    except Exception:  # noqa: BLE001
        return {"result": None, "error": "多智能体协作结果校验失败，请稍后重试"}

    return {"result": result, "error": None}
