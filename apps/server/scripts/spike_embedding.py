"""Spike：验证百炼 text-embedding-v3 走 OpenAI 兼容接口的可用性与维度。

用法（在 apps/server 下）：
    .venv/Scripts/python scripts/spike_embedding.py
"""
import asyncio

from openai import AsyncOpenAI

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    print("base_url :", settings.DASHSCOPE_BASE_URL)
    print("api_key  :", "已配置" if settings.DASHSCOPE_API_KEY else "【未配置】")
    if not settings.DASHSCOPE_API_KEY:
        print("请先在 .env 填入 DASHSCOPE_API_KEY")
        return

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )

    print("\n=== text-embedding-v3 单条 ===")
    resp = await client.embeddings.create(model="text-embedding-v3", input=["红烧肉怎么做不腻"])
    emb = resp.data[0].embedding
    print("维度:", len(emb))
    print("前 5 个值:", [round(x, 4) for x in emb[:5]])

    print("\n=== text-embedding-v3 批量（query 类型参数验证）===")
    try:
        resp2 = await client.embeddings.create(
            model="text-embedding-v3",
            input=["凉拌黄瓜", "红烧肉", "西红柿炒鸡蛋"],
            extra_body={"input_type": "query"},
        )
        dims = {len(d.embedding) for d in resp2.data}
        print("批量返回条数:", len(resp2.data), "维度集合:", dims)
    except Exception as exc:  # noqa: BLE001
        print("extra_body input_type 可能不受支持:", exc)
        resp2 = await client.embeddings.create(
            model="text-embedding-v3", input=["凉拌黄瓜", "红烧肉", "西红柿炒鸡蛋"]
        )
        print("无参数批量返回条数:", len(resp2.data), "维度:", len(resp2.data[0].embedding))

    print("\n✅ 若上方维度均为 1024，即可用于 pgvector VECTOR(1024)")


if __name__ == "__main__":
    asyncio.run(main())
