"""膳食规划 Agent（LangGraph：偏好注入→生成 3/7 天计划→Pydantic 校验→重试/降级）。

基于用户口味偏好（忌口/辣度/咸淡/技能）生成 3 天（今天/明天/后天）或 7 天（周一~周日）× 早中晚三餐，
每餐含菜品与估算千卡，每天含全天千卡与宏量营养（蛋白质/脂肪/碳水）。
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.ai import MealPlanSchema
from app.services.agents.recipe_agent import build_prefs_text
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

# {days} 由 run_planner 填充；{labels} 为日期标签串。
PLAN_SYSTEM_TEMPLATE = """你是资深营养师兼中餐厨师。基于用户的口味偏好，生成 {days} 天膳食计划（{labels}）。
只输出 JSON，不要多余文字。JSON 结构：
{{
  "days": [
    {{
      "day_label": "今天",
      "meals": [
        {{"name": "早餐", "total_kcal": 380, "dishes": [{{"name": "牛奶燕麦粥 + 水煮蛋"}}]}},
        {{"name": "午餐", "total_kcal": 560, "dishes": [{{"name": "番茄鸡蛋面"}}, {{"name": "凉拌黄瓜"}}]}},
        {{"name": "晚餐", "total_kcal": 420, "dishes": [{{"name": "清蒸鲈鱼"}}, {{"name": "蒜蓉西兰花"}}, {{"name": "糙米饭 1 碗"}}]}}
      ],
      "total_kcal": 1360,
      "protein_g": 55,
      "fat_g": 42,
      "carbs_g": 198
    }}
  ]
}}
要求：
- 必须恰好 {days} 天，每天必须恰好 3 餐（早/午/晚），每餐至少 1 道菜
- 每餐标注估算千卡；每天给出全天合计：total_kcal、protein_g（蛋白质克数）、fat_g（脂肪克数）、carbs_g（碳水化合物克数）
- 三餐总千卡控制在合理范围（参考：男性 1800-2400，女性 1400-2000），营养配比建议蛋白质 15-25%、脂肪 20-30%、碳水 50-60%
- 严格规避用户忌口/过敏原；按辣度/咸淡/厨艺技能调整菜品复杂度
- 菜品组合合理、易执行，适合厨房小白
安全要求：输出为通用膳食建议，不构成医疗/营养处方；对过敏原提示谨慎。"""


def _day_labels(days: int) -> str:
    return "周一、周二、周三、周四、周五、周六、周日" if days == 7 else "今天、明天、后天"


class PlanState(TypedDict, total=False):
    prefs: dict
    days: int
    retries: int
    result: dict | None
    error: str | None


def _route(state: PlanState) -> dict:
    return {"retries": 0}


async def _generate(state: PlanState) -> dict:
    days = state.get("days", 3)
    prefs_text = build_prefs_text(state.get("prefs") or {})
    system = PLAN_SYSTEM_TEMPLATE.format(days=days, labels=_day_labels(days))
    user_msg = (
        f"我的口味偏好：{prefs_text}。"
        f"请生成 {days} 天膳食计划，每餐给出菜品与估算千卡，每天给出热量/蛋白质/脂肪/碳水。"
    )
    try:
        data = await ainvoke_json(
            model=settings.DEEPSEEK_MODEL,
            system=system,
            user=user_msg,
            enable_search=False,  # 膳食规划基于营养学常识生成，无需联网
        )
        try:
            # 归一化：补齐 fat_g/carbs_g 等默认字段，保证落库数据形状一致
            parsed = MealPlanSchema.model_validate(data)
            return {"result": parsed.model_dump(), "error": None}
        except Exception:  # noqa: BLE001
            # 交给校验节点决定重试或降级
            return {"result": data, "error": None}
    except LLMError as exc:
        return {"error": str(exc)}


def _route_after_generate(state: PlanState) -> str:
    """校验：天数与请求一致且每天 3 餐字段完整，否则重试(≤AI_MAX_RETRIES)或降级。"""
    result = state.get("result")
    expected = state.get("days", 3)
    if result is not None:
        try:
            parsed = MealPlanSchema.model_validate(result)
            if len(parsed.days) == expected and all(len(d.meals) == 3 for d in parsed.days):
                return "accept"
        except Exception:  # noqa: BLE001
            pass
    if state.get("retries", 0) < settings.AI_MAX_RETRIES:
        return "retry"
    return "fallback"


def _retry(state: PlanState) -> dict:
    return {"retries": state.get("retries", 0) + 1}


async def _fallback(state: PlanState) -> dict:
    return {"result": None, "error": state.get("error") or "膳食计划生成失败，请稍后重试"}


def _build_graph():
    g = StateGraph(PlanState)
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


_plan_graph = _build_graph()


async def run_planner(prefs: dict | None = None, days: int = 3) -> dict:
    """运行膳食规划 Agent。返回 {"result": MealPlanSchema字典|None, "error": str|None}。"""
    state = await _plan_graph.ainvoke({"prefs": prefs or {}, "days": days})
    return {"result": state.get("result"), "error": state.get("error")}
