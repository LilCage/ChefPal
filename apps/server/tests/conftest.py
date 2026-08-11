"""pytest 共享夹具：测试库(chefpal_test)建表 + get_db 覆盖 + TestClient。"""
import asyncio
import os

os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  确保所有 ORM 注册到 metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.pgvector import make_pgvector_creator
from app.db.session import get_db
from app.main import app

settings = get_settings()

# NullPool：每条连接在其使用的事件循环内新建即用即弃，
# 规避 asyncpg 连接与 loop 绑定导致的"Event loop is closed / InterfaceError"
# async_creator：每个连接注册 pgvector vector 类型（recipe_kb 依赖）
test_engine = create_async_engine(
    settings.TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    async_creator=make_pgvector_creator(settings.TEST_DATABASE_URL),
)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    """路由内 DB 会话指向测试库。"""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _reset_test_db():
    """每个用例独立清空重建表，避免 ai_calls 等跨用例累积污染风控测试。"""

    async def reset():
        async with test_engine.begin() as conn:
            # 确保 pgvector 扩展可用（recipe_kb 的 VECTOR 列依赖；幂等）
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
async def db():
    """直接访问测试库会话（服务层单测用，如 recipe_kb 向量检索）。"""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture()
def make_headers(client, monkeypatch):
    """登录工厂：可指定 openid 创建多个独立测试用户。"""

    def _factory(openid: str = "openid-test"):
        from app.services import wechat as wechat_service

        async def _fake_code2session(code: str) -> dict:
            return {"openid": openid, "session_key": "mock-session"}

        monkeypatch.setattr(wechat_service, "code2session", _fake_code2session)
        token = client.post("/api/auth/login", json={"code": "code"}).json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    return _factory


@pytest.fixture()
def auth_headers(make_headers):
    """默认测试用户（openid-test）的鉴权头。"""
    return make_headers("openid-test")
