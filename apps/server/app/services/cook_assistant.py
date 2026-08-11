"""语音烹饪助手服务（EXT-14.1）：基于菜谱上下文回答做饭时的语音提问。

用户做饭时问"下一步做什么""放多少盐""要多久"，前端把语音转文字后连同菜谱上下文一起发来，
LLM 结合当前菜谱步骤给出口语化、简短、可执行的回答（含当前步骤定位）。
"""
from app.core.config import get_settings
from app.schemas.ai import CookAnswerSchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

COOK_SYSTEM = """你是贴心的大厨语音助手，正在陪用户做一道菜。用户会语音提问（做饭时双手不便，回答要简短口语）。
只输出 JSON，不要多余文字。JSON 结构：
{
  "answer": "直接回答用户的问题（一句话，20~50 字，可含具体火候/时长/用量）",
  "current_step": 数字
}
要求：
- current_step：根据用户问题判断 TA 大概做到第几步（1 起；不确定填 0）
- answer 要具体可执行：如"放多少盐"给出"一小勺约2克"；"下一步做什么"给出下一步做法
- 不要重复整段菜谱，只针对提问回答
安全要求：输出为通用烹饪建议，不构成医疗/营养处方。"""


class CookAssistantError(Exception):
    """语音烹饪助手 AI 回答失败。"""


def _steps_text(title: str, steps: list) -> str:
    """把菜谱步骤拼成上下文文本（第N步：标题——详情）。"""
    lines = []
    for i, st in enumerate(steps or [], start=1):
        detail = st.get("detail", "") if isinstance(st, dict) else ""
        lines.append(f"{i}. {st.get('title', '') if isinstance(st, dict) else st}：{detail}")
    if not lines:
        lines = ["（暂无步骤）"]
    return f"菜名：{title}\n" + "\n".join(lines)


async def answer_cooking_question(title: str, steps: list, question: str) -> dict:
    """基于菜谱上下文回答做饭问题，返回 CookAnswerSchema 字典。"""
    q = question.strip()
    if not q:
        raise CookAssistantError("没有听到问题，请再说一次")

    user_msg = f"{_steps_text(title, steps)}\n\n用户问：{q}"

    last_error = None
    for attempt in range(settings.AI_MAX_RETRIES + 1):
        try:
            data = await ainvoke_json(
                model=settings.DEEPSEEK_MODEL,
                system=COOK_SYSTEM,
                user=user_msg,
                enable_search=False,
            )
            parsed = CookAnswerSchema.model_validate(data)
            if parsed.answer.strip():
                return parsed.model_dump()
            last_error = "回答内容为空"
        except (LLMError, Exception) as exc:  # noqa: BLE001
            last_error = str(exc)
    raise CookAssistantError(last_error or "回答失败，请稍后重试")
