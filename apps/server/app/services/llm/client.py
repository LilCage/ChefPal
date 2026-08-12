"""百炼 DeepSeek 客户端封装。

- 走 OpenAI 兼容接口（base_url = DASHSCOPE_BASE_URL）
- 联网搜索通过 extra_body={"enable_search": True, "search_options": {...}} 开启
- 返回 JSON，由上层 Agent 用 Pydantic 校验（重试/降级）
"""
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()


class LLMError(Exception):
    """LLM 调用/解析失败。"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )


def _extract_json(text: str) -> str:
    """从模型输出中尽力提取首个 JSON 对象/数组。"""
    candidates = re.findall(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
    for c in candidates:
        try:
            json.loads(c)
            return c
        except json.JSONDecodeError:
            continue
    raise LLMError("模型输出中未找到合法 JSON")


async def ainvoke_json(
    *,
    model: str,
    system: str,
    user: str,
    history: list[dict] | None = None,
    enable_search: bool = False,
    search_options: dict[str, Any] | None = None,
) -> dict:
    """调用 DeepSeek 并解析为 JSON dict。

    history: 多轮对话上下文，[{"role": "user"/"assistant", "content": str}, ...]，
    插在 system 与当前问题之间（旧一轮在前、近一轮在后）。

    未配置 DASHSCOPE_API_KEY 时抛 LLMError（提示先填 .env），便于本地 mock 测试与集成测试区分。
    """
    if not settings.DASHSCOPE_API_KEY:
        raise LLMError("未配置 DASHSCOPE_API_KEY，请先在 apps/server/.env 中填入")

    client = _client()
    extra_body: dict[str, Any] = {}
    if enable_search:
        extra_body["enable_search"] = True
        if search_options:
            extra_body["search_options"] = search_options

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            extra_body=extra_body if extra_body else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM 调用失败: {exc}") from exc

    content = resp.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return json.loads(_extract_json(content))


async def astream_text(
    *,
    model: str,
    system: str,
    user: str,
    history: list[dict] | None = None,
    enable_search: bool = False,
    search_options: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """流式调用 DeepSeek，逐个 yield 文本增量（供 SSE 打字机）。

    history: 多轮对话上下文（同 ainvoke_json）。

    未配置 DASHSCOPE_API_KEY 时抛 LLMError。调用方负责累积完整文本。
    """
    if not settings.DASHSCOPE_API_KEY:
        raise LLMError("未配置 DASHSCOPE_API_KEY，请先在 apps/server/.env 中填入")

    client = _client()
    extra_body: dict[str, Any] = {}
    if enable_search:
        extra_body["enable_search"] = True
        if search_options:
            extra_body["search_options"] = search_options

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            extra_body=extra_body if extra_body else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM 调用失败: {exc}") from exc

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
