"""冰箱管家服务：食材临期状态计算 + 常见食材保质期推断 + AI 组合推荐。

对齐 services/shopping.py 的模式：AI 校验失败重试 ≤AI_MAX_RETRIES，仍失败抛 FridgeAdviceError。
"""
from datetime import datetime, timezone

from app.core.config import get_settings
from app.schemas.ai import FridgeAdviceSchema
from app.services.llm.client import LLMError, ainvoke_json

settings = get_settings()

# 常见食材保质期（天）：按名称关键词匹配，兜底 7 天
SHELF_DAYS_MAP: dict[str, int] = {
    "西红柿": 6, "鸡蛋": 14, "生菜": 6, "白菜": 7, "菠菜": 4, "青菜": 4, "黄瓜": 5,
    "西兰花": 6, "花菜": 6, "胡萝卜": 14, "土豆": 14, "洋葱": 21, "大蒜": 30, "姜": 30,
    "葱": 5, "青椒": 5, "辣椒": 10, "茄子": 5, "豆角": 5, "冬瓜": 14, "南瓜": 21,
    "玉米": 10, "香菇": 7, "蘑菇": 5, "金针菇": 3, "豆腐": 3, "豆浆": 2, "牛奶": 7,
    "酸奶": 14, "猪肉": 3, "牛肉": 3, "羊肉": 3, "鸡肉": 3, "鸡翅": 3, "鸡胸肉": 3,
    "排骨": 3, "鱼": 2, "鲈鱼": 2, "虾": 2, "三文鱼": 2, "螃蟹": 1, "培根": 7, "火腿": 7,
    "香肠": 21, "面包": 7, "馒头": 5, "面条": 14, "挂面": 180, "米": 365, "大米": 365,
    "面粉": 365, "酱油": 365, "生抽": 365, "蚝油": 365, "番茄酱": 180, "盐": 365, "糖": 365,
    "油": 365, "花生油": 365, "苹果": 10, "香蕉": 5, "橙子": 10, "梨": 10, "草莓": 3,
    "葡萄": 5, "西瓜": 5, "柠檬": 14, "猕猴桃": 7, "桃子": 5, "火龙果": 7, "榴莲": 5,
    "芒果": 5, "菠萝": 7,
}
DEFAULT_SHELF_DAYS = 7
# 状态阈值：≤1 天"今日清空"(now)，≤2 天"即将过期"(warn)，否则状态良好(ok)
EXPIRING_DAYS_LEFT = 2


def infer_shelf_days(name: str) -> int:
    """按食材名关键词推断保质期（天），未命中兜底 DEFAULT_SHELF_DAYS。"""
    for keyword, days in SHELF_DAYS_MAP.items():
        if keyword in name:
            return days
    return DEFAULT_SHELF_DAYS


def compute_status(added_at: datetime, best_before_days: int) -> dict:
    """计算临期状态：已放天数 / 剩余天数 / now|warn|ok。"""
    if added_at.tzinfo is None:
        added_at = added_at.replace(tzinfo=timezone.utc)
    days_stored = (datetime.now(timezone.utc) - added_at).days
    days_left = best_before_days - days_stored
    if days_left <= 1:
        status = "now"
    elif days_left <= EXPIRING_DAYS_LEFT:
        status = "warn"
    else:
        status = "ok"
    return {"days_stored": days_stored, "days_left": days_left, "status": status}


FRIDGE_ADVICE_SYSTEM = """你是冰箱管家。基于即将过期的食材，推荐 1-3 个组合菜，优先消耗临期食材。
只输出 JSON，不要多余文字。JSON 结构：
{
  "suggestions": [
    {"ingredients": ["西红柿", "鸡蛋"], "dish": "番茄炒蛋", "time_minutes": 20, "match_score": 92}
  ],
  "note": "还有 1 份挂面，可加做「番茄鸡蛋面」双保险"
}
要求：
- ingredients 只列实际用到的食材名
- dish 是菜名；time_minutes 是预计分钟数；match_score 是 0-100 匹配度
- 优先用临期食材做组合；若有其他冰箱食材可补充进 note 一句
安全要求：输出为通用烹饪建议，不构成医疗/营养处方。"""


class FridgeAdviceError(Exception):
    """冰箱管家 AI 组合推荐失败。"""


async def generate_advice(expiring: list[str], all_items: list[str] | None = None) -> dict:
    """基于临期食材生成组合菜建议（FridgeAdviceSchema 字典）。"""
    expiring = [n.strip() for n in expiring if n.strip()]
    if not expiring:
        raise FridgeAdviceError("没有即将过期的食材")

    user_msg = "即将过期食材：" + "、".join(expiring)
    if all_items:
        rest = [n for n in all_items if n.strip() and n not in expiring]
        if rest:
            user_msg += "\n冰箱里其他食材：" + "、".join(rest)

    last_error = None
    for attempt in range(settings.AI_MAX_RETRIES + 1):
        try:
            data = await ainvoke_json(
                model=settings.DEEPSEEK_MODEL,
                system=FRIDGE_ADVICE_SYSTEM,
                user=user_msg,
                enable_search=False,
            )
            parsed = FridgeAdviceSchema.model_validate(data)
            if len(parsed.suggestions) >= 1:
                return parsed.model_dump()
            last_error = "组合建议结构不完整"
        except (LLMError, Exception) as exc:  # noqa: BLE001
            last_error = str(exc)
    raise FridgeAdviceError(last_error or "生成组合建议失败，请稍后重试")
