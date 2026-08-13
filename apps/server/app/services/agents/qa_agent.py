"""问答 Agent（LangGraph：生成(可选联网搜索)→Pydantic 校验→重试/降级）+ 意图路由智能体。"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import QARouterOut, QASchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

QA_SYSTEM = """你是资深中餐大厨。用结构化 JSON 回答用户的厨艺问题，只输出 JSON 不要多余文字。
先判断用户真正想问什么，四选一输出：

知识库参考：用户消息末尾可能附有「美食库菜谱/技巧」参考块，请优先从参考中取材回答——
尤其推荐/搭配/一桌类问题，从参考里挑合适的菜并简要介绍；参考里没有的再自行补充，不要凭空编造菜名。

【秘诀/技巧】用户问"某菜怎么嫩/不腻/不粘/去腥/入味/才好吃/有什么秘诀"等，想要做菜诀窍而非完整菜谱 → 填：
- dish_name: 菜名（如"蒸蛋"）
- core_secret: 直接给 2~3 条核心诀窍/关键点（简短、可执行，如"水开再上锅""蛋液过筛"），不要展开完整步骤
- steps/ingredients/avoid_pitfalls: 填空数组（不展开菜谱）
- followup: 必填"需要我帮你查找「{菜名}」的完整菜谱吗？"

【多做法列表】用户问"某道菜怎么做/有哪些做法/怎么做才正宗"等，且该菜通常有多种做法流派 → 填：
- recommendations: 数组，每项一种做法 {name: 做法名（如"家常红烧肉"/"南派红烧肉"/"慢炖版"）, core_secret: 该做法 1~2 句话简介（风味特点、关键点、预估时间）, time_minutes: 预计分钟数, ingredients: 主要食材数组}
- 列出 2~4 种不同做法/流派，覆盖常见家庭/地区/时间差异；每种只需简要介绍，不要展开完整步骤
- core_secret: 给整份列表加一句友好口语开场白（如"好嘞！「红烧肉」有几种经典做法，我帮你列好啦～"），语气亲切自然，像朋友在厨房教你；dish_name/ingredients/steps/avoid_pitfalls 填空
- 仅当用户明确要求"完整步骤/详细教程"时才改为单菜全量输出

【单菜全量】用户明确要某道菜的完整菜谱/详细步骤 → 填：
- dish_name: 菜名（必填）
- core_secret: 核心秘诀，一句话点破关键
- ingredients: 食材清单（字符串数组）
- steps: 可执行步骤（字符串数组，写给厨房小白，明确火候与大致时长）
- avoid_pitfalls: 常见翻车点/避坑指南（字符串数组）
- recommendations: 不要填（null）

【多菜推荐】用户问"推荐几道/哪些菜/有什么好做的/换换口味"等，要求给多个不同选择 → 填：
- recommendations: 数组，每项一道菜 {name: 菜名, core_secret: 这道菜核心秘诀或做法一句话, time_minutes: 预计分钟数, ingredients: 主要食材数组}
- 推荐 3~4 道，覆盖不同荤素/风味；每道都要有清晰菜名
- 若用户要"一桌/招待/聚会/家宴"，注意荤素搭配、冷热搭配、汤菜主食平衡（硬菜+素菜+汤+主食），不要全是同一类
- core_secret: 给整份清单加一句友好口语开场白（如"好嘞！我帮你挑了 3 道，看看哪道合胃口～"），语气亲切自然；ingredients/steps/avoid_pitfalls 可留空或填空数组

通用字段：
- sources: 若使用了联网搜索的事实性内容，给出来源 URL 数组；否则为 []
安全要求：输出为通用烹饪建议，不构成医疗/营养处方；对可能引起过敏的食材保持谨慎提示。"""


ROUTER_SYSTEM = """你是 ChefPal 的"烹饪知识百科"意图路由智能体，专司判断用户到底想问什么。只输出 JSON，不要多余文字。
根据用户问题（含最近对话上下文）判断意图，四选一：
- recipe_lookup: 用户要某道菜的做法/菜谱/方子（如"红烧肉怎么做""给我糖醋排骨的方子""蒸蛋的做法"）
- technique_tips: 用户问做菜秘诀/技巧/口感问题（如"蒸蛋怎么蒸才嫩滑""怎么去腥""红烧肉怎么不腻""怎么入味"）——想要诀窍而非完整菜谱
- recommend_dishes: 用户要推荐几道菜/吃什么（如"推荐几道下饭菜""有什么快手菜""周末吃什么"）
- table_menu: 用户要一桌/一顿完整搭配（如"推荐一桌有面子的家常菜""招待朋友""一周晚餐安排""家宴"）
- general: 其他厨艺问题

输出字段：
- intent: 上列之一
- dish_name: 问题明确涉及的具体菜名（标准叫法，如"蒸蛋""红烧肉"；不涉及则为空）
- needs_full_recipe: 用户是否明确要完整步骤/详细菜谱（如"给我完整菜谱""详细步骤"）
- confidence: high/medium/low（对判断没把握时给 low）
注意：同样是"怎么做"，若偏"做法流派"→recipe_lookup；若偏"诀窍/口感/技巧"（怎么嫩/不腻/不粘/去腥）→technique_tips。"""


async def route_intent(question: str, history: list[dict] | None = None) -> dict:
    """意图路由：判断用户想问什么（查菜谱/问秘诀/推荐/一桌/其他）。

    失败/超时返回 general 兜底（由 AI 直接回答），不阻断主流程。
    """
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=ROUTER_SYSTEM,
            user=question,
            history=history or None,
        )
        parsed = QARouterOut.model_validate(data)
        return parsed.model_dump()
    except Exception:  # noqa: BLE001 路由失败兜底为 general
        return {"intent": "general", "dish_name": "", "needs_full_recipe": False, "confidence": "low"}


class QAState(TypedDict, total=False):
    question: str
    history: list[dict] | None  # 多轮上下文 [{role, content}, ...]
    enable_search: bool          # 是否开启联网搜索（KB 覆盖到则关）
    retries: int
    result: dict | None
    error: str | None


def _route(state: QAState) -> dict:
    """路由节点：记录重试计数。"""
    return {"retries": 0}


async def _generate(state: QAState) -> dict:
    """生成节点：调 DeepSeek（可按需联网）+ JSON。多轮时注入历史上下文。"""
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=QA_SYSTEM,
            user=state["question"],
            history=state.get("history"),
            enable_search=bool(state.get("enable_search", True)),
            search_options={"forced_search": True} if state.get("enable_search", True) else None,
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


async def run_qa(
    question: str,
    history: list[dict] | None = None,
    enable_search: bool = True,
) -> dict:
    """运行问答 Agent。返回 {"result": QASchema字典|None, "error": str|None}。

    enable_search=False 表示知识库已覆盖，不联网（更快更省，避免"免AI秒回"被联网拖慢）。
    """
    state = await _qa_graph.ainvoke(
        {"question": question, "history": history, "enable_search": enable_search}
    )
    return {"result": state.get("result"), "error": state.get("error")}
