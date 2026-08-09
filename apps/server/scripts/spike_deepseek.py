"""M0 技术验证 Spike：百炼 DeepSeek 联网搜索 + 结构化 JSON 输出。

用法（在 apps/server 下）：
    .venv/Scripts/python scripts/spike_deepseek.py
"""
import asyncio

from app.core.config import get_settings
from app.schemas.ai import QASchema
from app.services.llm.client import LLMError, ainvoke_json


async def main() -> None:
    settings = get_settings()
    print("model     :", settings.DEEPSEEK_MODEL)
    print("base_url  :", settings.DASHSCOPE_BASE_URL)
    print("api_key   :", "已配置" if settings.DASHSCOPE_API_KEY else "【未配置】")
    if not settings.DASHSCOPE_API_KEY:
        print("请先在 .env 填入 DASHSCOPE_API_KEY")
        return

    print("\n=== 调用 DeepSeek（联网搜索 + JSON）===")
    data = await ainvoke_json(
        model=settings.DEEPSEEK_MODEL,
        system=(
            "你是资深中餐大厨。用结构化 JSON 回答用户厨艺问题，只输出 JSON 不要多余文字。"
            "字段: core_secret(核心秘诀), ingredients(食材数组), steps(步骤数组), "
            "avoid_pitfalls(避坑数组), sources(来源URL数组，无则[])。"
        ),
        user="红烧肉怎么做不腻？",
        enable_search=settings.AI_ENABLE_SEARCH,
        search_options={"forced_search": True},
    )
    print("=== 原始 JSON ===")
    print(data)

    parsed = QASchema.model_validate(data)
    print("\n=== Pydantic 校验通过 ✓ ===")
    print("核心秘诀:", parsed.core_secret)
    print("步骤数  :", len(parsed.steps))
    print("避坑数  :", len(parsed.avoid_pitfalls))
    print("来源    :", parsed.sources)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except LLMError as exc:
        print("\n❌ LLM 调用失败:", exc)
