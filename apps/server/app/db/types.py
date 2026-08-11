"""通用列类型：JSONB（PG）/ JSON（其他方言）双兼容 + pgvector 向量列。"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from pgvector.sqlalchemy import VECTOR as _PgVECTOR

# PG 上落 JSONB，SQLite 等方言回落普通 JSON，方便本地测试。
JSONType = JSON().with_variant(JSONB, "postgresql")


class VectorType(_PgVECTOR):
    """pgvector VECTOR 列类型，覆盖 bind_processor。

    默认实现把 list 字符串化为 '[1.0,2.0]'，而 asyncpg 的 vector codec
    期望 list/ndarray（Vector(str) 抛 ValueError）。改为原样透传，
    由 asyncpg codec（app/db/pgvector.py 的 register_vector）负责编码。
    """

    cache_ok = True  # 状态仅 dim，可安全参与语句缓存

    def bind_processor(self, dialect):
        def process(value):
            return value

        return process
