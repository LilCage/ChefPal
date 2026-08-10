"""add recipes.style column (推荐风味标签，TOP3 多样性校验)

Revision ID: e4d7a2c8f5b6
Revises: c3f5a9d21b7e
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4d7a2c8f5b6'
down_revision: Union[str, None] = 'c3f5a9d21b7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'recipes',
        sa.Column('style', sa.String(length=16), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('recipes', 'style')
    # ### end Alembic commands ###
