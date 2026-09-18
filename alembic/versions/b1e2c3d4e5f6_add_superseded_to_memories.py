"""add superseded column to memories

Revision ID: b1e2c3d4e5f6
Revises: 2495bfcff9d1
Create Date: 2026-09-18 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1e2c3d4e5f6'
down_revision: Union[str, None] = '2495bfcff9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'memories',
        sa.Column('superseded', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('memories', 'superseded')
