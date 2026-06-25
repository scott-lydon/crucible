"""add cancel_requested to runs

Adds a defaulted ``cancel_requested`` boolean to ``runs`` so a run can be
cooperatively cancelled across the worker-subprocess boundary: ``POST
/runs/{id}/stop`` sets the flag, the run loop polls it between rounds and exits
to the ``stopped`` terminal status. Server-defaulted to false so existing rows
read as not-cancelled; nullable keeps the ADD COLUMN dialect-neutral.

Revision ID: b2e1f7c4d9a3
Revises: a1c0de9a2b10
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2e1f7c4d9a3"
down_revision: Union[str, Sequence[str], None] = "a1c0de9a2b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "runs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=True,
            # ``sa.false()`` renders per-dialect (``false`` on Postgres, ``0`` on
            # SQLite) — a bare ``0`` literal would be rejected by Postgres's
            # strict boolean typing. So existing rows read as not-cancelled.
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "cancel_requested")
