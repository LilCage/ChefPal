"""问答 Agent（LangGraph：路由→生成(联网搜索)→Pydantic 校验→重试/降级）。"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import QASchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

QA_SYSTEM = """你是资深中餐大厨。用结构化 JSON 回答用户的厨艺问题，只输出 JSON 不要多余文字。
字段定义：
- core_secret: 核心秘诀，一句话点破关键
- ingredients: 食材清单（字符串数组）
- steps: 可执行步骤（字符串数组，写给厨房小白，明确火候与大致时长）
- avoid_pitfalls: 常见翻车点/避坑指南（字符串数组）
- sources: 若使用了联网搜索的事实性内容，给出来源 URL 数组；否则为 []
安全要求：输出为通用烹饪建议，不构成医疗/营养处方；对可能引起过敏的食材保持谨慎提示。"""


class QAState(TypedDict, total=False):
    question: str
    retries: int
    result: dict | None
    error: str | None


def _route(state: QAState) -> dict:
    """路由节点：厨艺问题默认开启联网搜索（P0 必需）。"""
    return {"retries": 0}


async def _generate(state: QAState) -> dict:
    """生成节点：调 DeepSeek（enable_search 联网）+ JSON。"""
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=QA_SYSTEM,
            user=state["question"],
            enable_search=settings.AI_ENABLE_SEARCH,
            search_options={"forced_search": True},
        )
        return {"result": data, "error": None}
    except LLMError as exc:
        return {"error": str(exc)}


def _route_after_generate(state: QAState) -> str:
    """校验节点（条件边）：通过→accept；失败且可重试→retry；否则→fallback。"""
    result = state.get("result")
    if result is not None:
        try:
            QASchema.model_validate(result)
            return "accept"
        except Exception:  # noqa: BLE001  结构化校验失败
            pass
    if state.get("retries", 0) < settings.AI_MAX_RETRIES:
        return "retry"
    return "fallback"


def _retry(state: QAState) -> dict:
    return {"retries": state.get("retries", 0) + 1}


async def _fallback(state: QAState) -> dict:
    return {"result": None, "error": state.get("error") or "AI 生成失败，请稍后重试"}


def _build_graph():
    g = StateGraph(QAState)
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


_qa_graph = _build_graph()


async def run_qa(question: str) -> dict:
    """运行问答 Agent。返回 {"result": QASchema字典|None, "error": str|None}。"""
    state = await _qa_graph.ainvoke({"question": question})
    return {"result": state.get("result"), "error": state.get("error")}
