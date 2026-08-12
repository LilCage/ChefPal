"""add qa_records.session_id (多轮对话会话)

Revision ID: b3a9c8d7e6f5
Revises: 9c8d7e6f5a4b
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3a9c8d7e6f5'
down_revision: Union[str, None] = '9c8d7e6f5a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('qa_records', sa.Column('session_id', sa.Uuid(), nullable=True))
    op.create_index('ix_qa_records_session_id', 'qa_records', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_qa_records_session_id', table_name='qa_records')
    op.drop_column('qa_records', 'session_id')
