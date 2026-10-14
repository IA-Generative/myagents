"""add guard events

Revision ID: c3f5a7b9d124
Revises: b2e4f6a8c013
Create Date: 2026-10-05 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f5a7b9d124"
down_revision: str | Sequence[str] | None = "b2e4f6a8c013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guard_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("route", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guard_events_created_at"),
        "guard_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guard_events_user_id"), "guard_events", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_guard_events_user_id"), table_name="guard_events")
    op.drop_index(op.f("ix_guard_events_created_at"), table_name="guard_events")
    op.drop_table("guard_events")
