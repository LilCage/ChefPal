"""异步数据库引擎与会话。"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.pgvector import make_pgvector_creator

settings = get_settings()

# async_creator 在每个连接上注册 pgvector vector 类型（recipe_kb 向量检索依赖）
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    async_creator=make_pgvector_creator(settings.DATABASE_URL),
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供一个数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session
