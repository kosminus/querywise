"""Scheduled reports (Phase 4 — Milestone 2)

Revision ID: 010
Revises: 009
Create Date: 2026-06-08

Adds ``schedules`` — recurring delivery of a saved query or dashboard on a cron
schedule over a notification channel (email/Slack/log), with optional
alert-on-threshold. Workspace-scoped like dashboards. The scheduler claims due
rows on ``next_run_at``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cron", sa.String(120), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("recipients", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("threshold", JSONB, nullable=True),
        sa.Column(
            "only_on_threshold", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # The scheduler scans for enabled, due rows ordered by next_run_at.
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])
    op.create_index("ix_schedules_workspace_id", "schedules", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_schedules_workspace_id", table_name="schedules")
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_table("schedules")
