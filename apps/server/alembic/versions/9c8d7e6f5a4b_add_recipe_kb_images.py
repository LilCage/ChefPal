"""add_recipe_kb_images (知识库菜谱成品图)

Revision ID: 9c8d7e6f5a4b
Revises: 8a9b0c1d2e3f
Create Date: 2026-08-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9c8d7e6f5a4b'
down_revision: Union[str, None] = '8a9b0c1d2e3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipe_kb', sa.Column('images', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('recipe_kb', 'images')
