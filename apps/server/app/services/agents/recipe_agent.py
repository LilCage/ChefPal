"""菜谱 Agent（LangGraph：食材分析→偏好注入→TOP3→Pydantic 校验→重试/降级）。

核心差异化功能：基于用户现有食材 + 口味偏好实时生成 TOP3 菜谱。
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import RecipeSetSchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

RECIPE_SYSTEM = """你是资深中餐厨师。基于用户现有食材与口味偏好，生成 3 道可行性最高的菜（TOP3）。
只输出 JSON，不要多余文字。JSON 结构：
{
  "recipes": [
    {
      "name": "菜名",
      "match_score": 0-100,
      "time_minutes": 预计耗时分钟数,
      "difficulty": "简单|中等|较难",
      "style": "风味标签，如 浓香下饭/清爽快手/蒸煮清淡/香辣过瘾/甜口绵密/汤羹温润",
      "missing_seasonings": ["缺少的调料，尽量给替代方案"],
      "steps": [{"title": "步骤名", "detail": "详细做法（写给厨房小白，明确火候与大致时长）"}],
      "tips": ["避坑指南"]
    }
  ]
}
硬性要求：
- 【多样性·最重要】3 道菜必须风味、做法、荤素差异明显，风格标签（style）至少 2 种不同，禁止 3 道高度重合
- 即使口味偏好偏重口/辛辣，也必须至少包含 1 道清淡、清爽或换口味的菜，供用户换口味
- 优先使用用户现有食材，匹配度 match_score 越高越好
- 每道必须给出完整可执行的 steps，至少 3 步
- 严格规避用户忌口/过敏原，并在 tips 中提示
安全要求：输出为通用烹饪建议，不构成医疗/营养处方；对过敏原提示谨慎。"""


def build_prefs_text(prefs: dict) -> str:
    """把偏好字典转成可注入的自然语言片段。"""
    if not prefs:
        return "无特殊偏好"
    parts = []
    if prefs.get("allergies"):
        parts.append("忌口/过敏原: " + "、".join(prefs["allergies"]))
    spiciness = {0: "不吃辣", 1: "微辣", 2: "中辣", 3: "特辣"}.get(prefs.get("spiciness"))
    if spiciness:
        parts.append(f"辣度: {spiciness}")
    if prefs.get("saltiness"):
        parts.append(f"咸淡: {prefs['saltiness']}")
    if prefs.get("skill"):
        parts.append(f"厨艺技能: {prefs['skill']}")
    if prefs.get("taste_memory"):
        parts.append(f"口味记忆(来自收藏/点赞): {prefs['taste_memory']}")
    return "；".join(parts) if parts else "无特殊偏好"


class RecipeState(TypedDict, total=False):
    ingredients: list[str]
    prefs: dict
    retries: int
    result: dict | None
    error: str | None
    retry_note: str | None  # 上次失败的修正指令，重试时追加到 user 消息


def _route(state: RecipeState) -> dict:
    return {"retries": 0}


async def _generate(state: RecipeState) -> dict:
    ingredients = "、".join(state["ingredients"])
    prefs_text = build_prefs_text(state.get("prefs") or {})
    user_msg = f"我冰箱里现有食材：{ingredients}。我的口味偏好：{prefs_text}。请生成 3 道可行性最高的菜。"
    note = state.get("retry_note")
    if note:
        user_msg += f"\n\n{note}"
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=RECIPE_SYSTEM,
            user=user_msg,
            enable_search=False,  # 菜谱生成不需要联网，用模型厨艺知识即可
        )
        return {"result": data, "error": None}
    except LLMError as exc:
        return {"error": str(exc)}


def _route_after_generate(state: RecipeState) -> str:
    """校验：至少 3 道、字段完整、且风格多样性（style 去重 ≥2 种），否则重试或降级。"""
    result = state.get("result")
    if result is not None:
        try:
            parsed = RecipeSetSchema.model_validate(result)
            styles = {r.style for r in parsed.recipes if r.style}
            if len(parsed.recipes) >= 3 and len(styles) >= 2:
                return "accept"
        except Exception:  # noqa: BLE001
            pass
    if state.get("retries", 0) < settings.AI_MAX_RETRIES:
        return "retry"
    return "fallback"


def _retry(state: RecipeState) -> dict:
    return {
        "retries": state.get("retries", 0) + 1,
        "retry_note": (
            "上一版 3 道菜风味过于重合。请重新生成：3 道菜的风味标签（style）必须至少 2 种不同，"
            "做法/荤素也要拉开差异；如果偏好偏重口/辛辣，请务必加入至少 1 道清淡或清爽的菜。"
        ),
    }


async def _fallback(state: RecipeState) -> dict:
    return {"result": None, "error": state.get("error") or "菜谱生成失败，请稍后重试"}


def _build_graph():
    g = StateGraph(RecipeState)
    g.add_node("route", _route)
    g.add_node("generate", _generate)
    g.add_node("retry", _retry)
    g.add_node("fallback", _fallback)

    g.add_edge(START, "route")
    g.add_edge("route", "generate")
    g.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"accept": END, "retry": "retry", "fallback": "fallback"},
    )
    g.add_edge("retry", "generate")
    g.add_edge("fallback", END)
    return g.compile()


_recipe_graph = _build_graph()


async def run_recipe(ingredients: list[str], prefs: dict | None = None) -> dict:
    """运行菜谱 Agent。返回 {"result": RecipeSetSchema字典|None, "error": str|None}。"""
    state = await _recipe_graph.ainvoke(
        {"ingredients": ingredients, "prefs": prefs or {}}
    )
    return {"result": state.get("result"), "error": state.get("error")}
