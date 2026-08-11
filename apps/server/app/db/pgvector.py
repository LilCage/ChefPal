"""asyncpg + pgvector 类型注册：每个连接建立时注册 vector codec。

asyncpg 原生不认识 pgvector 的 vector 类型，必须在连接上 set_type_codec。
SQLAlchemy async engine 用 async_creator 自定义连接工厂，在连接建立后注册。
"""
import asyncpg
from pgvector.asyncpg import register_vector


def make_pgvector_creator(url: str):
    """返回 async_creator：建立 asyncpg 连接后注册 pgvector 类型。

    url 形如 postgresql+asyncpg://...，asyncpg.connect 需要去掉 +asyncpg。
    """

    dsn = url.replace("+asyncpg", "")

    async def creator() -> asyncpg.Connection:
        conn = await asyncpg.connect(dsn)
        await register_vector(conn)
        return conn

    return creator
