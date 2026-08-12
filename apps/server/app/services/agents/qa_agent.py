"""问答 Agent（LangGraph：路由→生成(联网搜索)→Pydantic 校验→重试/降级）。"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import QASchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

QA_SYSTEM = """你是资深中餐大厨。用结构化 JSON 回答用户的厨艺问题，只输出 JSON 不要多余文字。
先判断问题类型，二选一输出：

【类型一 · 单菜做法】用户问"某道菜怎么做/怎么不腻/怎么嫩"等具体做法 → 填：
- dish_name: 菜名（必填）
- core_secret: 核心秘诀，一句话点破关键
- ingredients: 食材清单（字符串数组）
- steps: 可执行步骤（字符串数组，写给厨房小白，明确火候与大致时长）
- avoid_pitfalls: 常见翻车点/避坑指南（字符串数组）
- recommendations: 不要填（null）

【类型二 · 多菜推荐】用户问"推荐几道/哪些菜/有什么好做的/换换口味"等，要求给多个选择 → 填：
- recommendations: 数组，每项一道菜 {name: 菜名, core_secret: 这道菜核心秘诀或做法一句话, time_minutes: 预计分钟数, ingredients: 主要食材数组}
- 推荐 3~4 道，覆盖不同荤素/风味；每道都要有清晰菜名
- core_secret/ingredients/steps/avoid_pitfalls 可留空或填空数组

通用字段：
- sources: 若使用了联网搜索的事实性内容，给出来源 URL 数组；否则为 []
安全要求：输出为通用烹饪建议，不构成医疗/营养处方；对可能引起过敏的食材保持谨慎提示。"""


class QAState(TypedDict, total=False):
    question: str
    history: list[dict] | None  # 多轮上下文 [{role, content}, ...]
    retries: int
    result: dict | None
    error: str | None


def _route(state: QAState) -> dict:
    """路由节点：厨艺问题默认开启联网搜索（P0 必需）。"""
    return {"retries": 0}


async def _generate(state: QAState) -> dict:
    """生成节点：调 DeepSeek（enable_search 联网）+ JSON。多轮时注入历史上下文。"""
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=QA_SYSTEM,
            user=state["question"],
            history=state.get("history"),
            enable_search=settings.AI_ENABLE_SEARCH,
            search_options={"forced_search": True},
        )
        return {"result": data, "error": None}
    except LLMError as exc:
        return {"error": str(exc)}


def _route_after_generate(state: QAState) -> str:
    """校验节点（条件边）：通过→accept；失败且可重试→retry；否则→fallback。

    语义校验：单菜型必须含 dish_name + steps；推荐型必须含非空 recommendations。
    避免 schema 放宽（默认值兜底）后空壳回答也能通过。
    """
    result = state.get("result")
    if result is not None:
        try:
            parsed = QASchema.model_validate(result)
            has_recs = bool(parsed.recommendations)
            has_single = bool(parsed.dish_name.strip()) and len(parsed.steps) >= 1
            if has_recs or has_single:
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


async def run_qa(question: str, history: list[dict] | None = None) -> dict:
    """运行问答 Agent。返回 {"result": QASchema字典|None, "error": str|None}。"""
    state = await _qa_graph.ainvoke({"question": question, "history": history})
    return {"result": state.get("result"), "error": state.get("error")}
