"""链接/文档解析 Agent：从提取的文本（网页正文/视频字幕/文档）中结构化出菜谱。

复用 QASchema（单菜做法结构），供前端以与问答一致的分段式卡片渲染。
"""
from app.core.config import get_settings
from app.schemas.ai import QASchema
from app.services.llm.client import ainvoke_json

settings = get_settings()

PARSE_SYSTEM = """你是资深中餐大厨。下面给出【来源内容】（可能是菜谱网页正文、做菜视频字幕、或 PDF/Word 菜谱文档），
请从中提取出这道菜谱，输出结构化 JSON，只输出 JSON 不要多余文字：
- dish_name: 菜名（必填）
- core_secret: 核心秘诀，一句话点破关键（从原文提炼，不要编造）
- ingredients: 完整食材清单（尽量带用量，字符串数组；原文没有用量则只写食材名）
- steps: 可执行做法步骤（字符串数组，写给厨房小白，明确火候与大致时长；尽量还原原文步骤顺序，用"1. "开头）
- prep_steps: 食材处理步骤（切/洗/腌/焯等，可空数组）
- cook_steps: 烹饪步骤（下锅/调味/出锅等，可空数组；无切分时放 steps）
- avoid_pitfalls: 常见翻车点/避坑（字符串数组；原文没有则可留空）
- sources: []
- recommendations: null

规则：只从给出的内容中提取，不要外推或补全原文没有的步骤；
若内容不含菜谱做法（如只是食材科普），dish_name 可为空，steps 留空，并在 core_secret 说明内容性质。
安全要求：输出为通用烹饪建议，不构成医疗/营养处方。"""

_MAX_CONTENT = 4000  # 防止超长文档超出模型上下文


async def run_parse(source_label: str, content: str) -> dict:
    """解析提取文本 → QASchema 字典。返回前做语义校验：必须识别出菜名。"""
    user = f"【来源】{source_label}\n【内容】\n{content[:_MAX_CONTENT]}"
    data = await ainvoke_json(
        model=settings.DEEPSEEK_MODEL,
        system=PARSE_SYSTEM,
        user=user,
    )
    parsed = QASchema.model_validate(data)
    if not parsed.dish_name.strip():
        raise ValueError("未能从内容中识别出菜名，请换一个更完整的来源")
    return data
