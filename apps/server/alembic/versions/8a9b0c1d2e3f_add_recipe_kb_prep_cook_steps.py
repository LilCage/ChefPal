"""add_recipe_kb_prep_cook_steps (知识库步骤切分：食材处理/烹饪步骤)

Revision ID: 8a9b0c1d2e3f
Revises: 7f6e5d4c3b2a
Create Date: 2026-08-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a9b0c1d2e3f'
down_revision: Union[str, None] = '7f6e5d4c3b2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipe_kb', sa.Column('prep_steps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))
    op.add_column('recipe_kb', sa.Column('cook_steps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('recipe_kb', 'cook_steps')
    op.drop_column('recipe_kb', 'prep_steps')
