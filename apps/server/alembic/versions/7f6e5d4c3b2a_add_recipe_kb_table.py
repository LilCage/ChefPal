"""add_recipe_kb_table (菜谱知识库 + pgvector)

Revision ID: 7f6e5d4c3b2a
Revises: 99f113b78b24
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7f6e5d4c3b2a'
down_revision: Union[str, None] = '99f113b78b24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 确保 pgvector 扩展可用（旧数据卷容器 init 脚本不会重跑，故迁移内兜底）
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table('recipe_kb',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('ingredients', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('steps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('tips', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('time_minutes', sa.Integer(), nullable=False),
    sa.Column('difficulty', sa.String(length=16), nullable=False),
    sa.Column('style', sa.String(length=16), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.Column('source_id', sa.String(length=64), nullable=False),
    sa.Column('hit_count', sa.Integer(), nullable=False),
    sa.Column('embedding', VECTOR(dim=1024), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recipe_kb_kind_title'), 'recipe_kb', ['kind', 'title'], unique=False)
    op.create_index(op.f('ix_recipe_kb_source'), 'recipe_kb', ['source_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_recipe_kb_source'), table_name='recipe_kb')
    op.drop_index(op.f('ix_recipe_kb_kind_title'), table_name='recipe_kb')
    op.drop_table('recipe_kb')
