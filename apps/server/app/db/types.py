"""通用列类型：JSONB（PG）/ JSON（其他方言）双兼容。"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# PG 上落 JSONB，SQLite 等方言回落普通 JSON，方便本地测试。
JSONType = JSON().with_variant(JSONB, "postgresql")
