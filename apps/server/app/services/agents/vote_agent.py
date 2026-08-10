"""家庭口味投票 Agent：基于冰箱食材 + 口味偏好生成 3 道候选菜（原型 05 屏2）。

与 recipe_agent 不同：只输出菜名（投票选项），不做完整步骤，调用更轻量省钱。
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import VoteOptionsSchema
from app.services.agents.recipe_agent import build_prefs_text
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

VOTE_SYSTEM = """你是家庭晚餐决策助手。基于用户冰箱里现有食材与全家口味偏好，推荐 3 道菜让全家人投票决定今晚吃什么。
只输出 JSON，不要多余文字。JSON 结构：
{
  "options": ["菜名1", "菜名2", "菜名3"]
}
硬性要求：
- 3 道菜必须风味/做法/荤素差异明显（一道清淡、一道下饭、一道快手换口味）
- 优先使用冰箱现有食材
- 严格规避全家忌口/过敏原
安全要求：输出为通用烹饪建议，不构成医疗/营养处方。"""


class VoteState(TypedDict, total=False):
    ingredients: list[str]
    prefs: dict
    retries: int
    result: dict | None
    error: str | None


async def _generate(state: VoteState) -> dict:
    ingredients = "、".join(state["ingredients"])
    prefs_text = build_prefs_text(state.get("prefs") or {})
    user_msg = f"冰箱现有食材：{ingredients}。全家口味偏好：{prefs_text}。请推荐 3 道菜供家庭投票。"
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=VOTE_SYSTEM,
            user=user_msg,
            enable_search=False,
        )
        return {"result": data, "error": None}
    except LLMError as exc:
        return {"error": str(exc)}


def _validate(state: VoteState) -> str:
    result = state.get("result")
    if result is not None:
        try:
            parsed = VoteOptionsSchema.model_validate(result)
            if len(parsed.options) == 3:
                return "accept"
        except Exception:  # noqa: BLE001
            pass
    if state.get("retries", 0) < settings.AI_MAX_RETRIES:
        return "retry"
    return "fallback"


def _retry(state: VoteState) -> dict:
    return {"retries": state.get("retries", 0) + 1}


async def _fallback(state: VoteState) -> dict:
    return {"result": None, "error": state.get("error") or "选项生成失败，请稍后重试"}


def _build_graph():
    g = StateGraph(VoteState)
    g.add_node("generate", _generate)
    g.add_node("retry", _retry)
    g.add_node("fallback", _fallback)
    g.add_edge(START, "generate")
    g.add_conditional_edges(
        "generate",
        _validate,
        {"accept": END, "retry": "retry", "fallback": "fallback"},
    )
    g.add_edge("retry", "generate")
    g.add_edge("fallback", END)
    return g.compile()


_vote_graph = _build_graph()


async def run_vote(ingredients: list[str], prefs: dict | None = None) -> dict:
    """运行投票 Agent。返回 {"result": {"options": [...]} | None, "error": str|None}。"""
    state = await _vote_graph.ainvoke({"ingredients": ingredients, "prefs": prefs or {}})
    return {"result": state.get("result"), "error": state.get("error")}
