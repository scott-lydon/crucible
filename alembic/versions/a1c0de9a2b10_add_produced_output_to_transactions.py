"""add produced_output to transactions

Adds a nullable ``produced_output`` text column to ``transactions`` so a
PRODUCE-victim's artifact (e.g. the source code a code agent wrote) is auditable
per-row. NULL for the fraud classifier (whose produced output is its score), so
the existing fraud path is byte-identical.

Revision ID: a1c0de9a2b10
Revises: d80229e5a45c
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c0de9a2b10"
down_revision: Union[str, Sequence[str], None] = "d80229e5a45c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "transactions",
        sa.Column("produced_output", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transactions", "produced_output")
