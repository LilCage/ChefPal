"""百炼 text-embedding-v3 文本向量服务（菜谱知识库 RAG）。

与 llm/client.py 同一套 OpenAI 兼容接口（base_url = DASHSCOPE_BASE_URL）。
未配置 DASHSCOPE_API_KEY 时抛 EmbeddingError，便于测试 mock 与集成测试区分。
"""
from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()


class EmbeddingError(Exception):
    """Embedding 调用/配置失败。"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )


async def aembed_texts(texts: list[str], *, input_type: str = "document") -> list[list[float]]:
    """批量计算文本向量（settings.EMBEDDING_DIM 维）。

    input_type: "document"（入库内容）/ "query"（检索问题），text-embedding-v3 据此优化表征。
    """
    if not settings.DASHSCOPE_API_KEY:
        raise EmbeddingError("未配置 DASHSCOPE_API_KEY，无法计算向量")
    if not texts:
        return []

    client = _client()
    try:
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            extra_body={"input_type": input_type},
        )
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"Embedding 调用失败: {exc}") from exc
    return [d.embedding for d in resp.data]


async def aembed_text(text: str, *, input_type: str = "document") -> list[float]:
    """单条文本向量。"""
    out = await aembed_texts([text], input_type=input_type)
    return out[0]
