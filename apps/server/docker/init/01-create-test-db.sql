-- 创建 TDD 测试专用数据库（容器首次启动时自动执行）
CREATE DATABASE chefpal_test;

-- RAG 向量检索依赖 pgvector 扩展（pgvector/pgvector:pg16 镜像已内置二进制）
-- 主库 chefpal 的扩展由 Alembic 迁移执行；这里为测试库预建，便于 conftest 直接建表
\connect chefpal_test
CREATE EXTENSION IF NOT EXISTS vector;
\connect chefpal
CREATE EXTENSION IF NOT EXISTS vector;
