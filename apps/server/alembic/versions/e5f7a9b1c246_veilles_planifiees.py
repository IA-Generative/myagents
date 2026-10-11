"""veilles planifiées (chantier 3) : schedules, schedule_runs, veille_resultats

Revision ID: e5f7a9b1c246
Revises: d4e6f8a0b135
Create Date: 2026-10-11 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f7a9b1c246"
down_revision: str | Sequence[str] | None = "d4e6f8a0b135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("capability_name", sa.String(64), nullable=False),
        sa.Column("sujet", sa.String(200), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "conservation_jours", sa.Integer(), nullable=False, server_default="90"
        ),
        sa.Column("derniere_execution", _TZ, nullable=True),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("updated_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedules_sub", "schedules", ["sub"])
    op.create_table(
        "schedule_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "schedule_id", sa.Uuid(), sa.ForeignKey("schedules.id"), nullable=False
        ),
        sa.Column("slot", _TZ, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="en_cours"),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "slot", name="uq_schedule_runs_slot"),
    )
    op.create_index("ix_schedule_runs_schedule_id", "schedule_runs", ["schedule_id"])
    op.create_table(
        "veille_resultats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "schedule_id", sa.Uuid(), sa.ForeignKey("schedules.id"), nullable=False
        ),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("synthese", sa.Text(), nullable=False),
        sa.Column("generated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("urls_consultees", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for colonne in ("schedule_id", "sub", "created_at", "expires_at"):
        op.create_index(f"ix_veille_resultats_{colonne}", "veille_resultats", [colonne])


def downgrade() -> None:
    for colonne in ("schedule_id", "sub", "created_at", "expires_at"):
        op.drop_index(f"ix_veille_resultats_{colonne}", table_name="veille_resultats")
    op.drop_table("veille_resultats")
    op.drop_index("ix_schedule_runs_schedule_id", table_name="schedule_runs")
    op.drop_table("schedule_runs")
    op.drop_index("ix_schedules_sub", table_name="schedules")
    op.drop_table("schedules")
