"""workspace_policy and run_overrides tables

Revision ID: a1b2c3d4e5f6
Revises: ec4dc1906055
Create Date: 2026-06-24 14:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "ec4dc1906055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_policy",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("policy_yaml", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "run_overrides",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("run_overrides")
    op.drop_table("workspace_policy")
