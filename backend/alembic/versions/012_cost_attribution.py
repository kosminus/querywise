"""Cost & usage attribution (Phase 4 — Milestone 4)

Revision ID: 012
Revises: 011
Create Date: 2026-06-08

Adds ``cost_attributions`` — per-execution usage + estimated cost, attributed to
a workspace/user/connection. Powers the usage analytics dashboards (slowest
queries, error rate, most-queried tables, cost per team). Populated best-effort
after each query execution.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_attributions",
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
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "query_execution_id",
            UUID(as_uuid=True),
            sa.ForeignKey("query_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_provider", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("execution_time_ms", sa.Float, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("scanned_bytes", sa.Integer, nullable=True),
        sa.Column("slot_ms", sa.Integer, nullable=True),
        sa.Column("dbu", sa.Float, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("tables", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_cost_attributions_created_at", "cost_attributions", ["created_at"])
    op.create_index(
        "ix_cost_attributions_org_created",
        "cost_attributions",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_attributions_org_created", table_name="cost_attributions")
    op.drop_index("ix_cost_attributions_created_at", table_name="cost_attributions")
    op.drop_table("cost_attributions")
