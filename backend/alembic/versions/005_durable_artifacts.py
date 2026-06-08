"""Durable analytics artifacts (Phase 2 — Milestone 1)

Revision ID: 005
Revises: 004
Create Date: 2026-06-08

Adds the first durable-artifact tables: saved_queries (named, owned,
re-runnable question + pinned SQL + typed params), charts (a persisted
visualization config per saved query), and result_snapshots (persisted
results that double as the result cache, keyed by sql_hash + taken_at).

All tables are connection-scoped (the workspace cascade root) and carry
organization_id for SaaS-readiness, matching the Phase-1 metadata pattern.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_queries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("nl_question", sa.Text, nullable=True),
        sa.Column("pinned_sql", sa.Text, nullable=False),
        sa.Column("params", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_saved_queries_connection_id", "saved_queries", ["connection_id"])

    op.create_table(
        "charts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_query_id",
            UUID(as_uuid=True),
            sa.ForeignKey("saved_queries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("config", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_charts_saved_query_id", "charts", ["saved_query_id"])

    op.create_table(
        "result_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_query_id",
            UUID(as_uuid=True),
            sa.ForeignKey("saved_queries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sql_hash", sa.String(64), nullable=False),
        sa.Column("columns", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("column_types", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rows", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("params_used", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("execution_time_ms", sa.Float, nullable=True),
        sa.Column("truncated", sa.Boolean, server_default=sa.text("false")),
        sa.Column("taken_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_result_snapshots_sql_hash_taken_at",
        "result_snapshots",
        ["sql_hash", sa.text("taken_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_result_snapshots_sql_hash_taken_at", table_name="result_snapshots")
    op.drop_table("result_snapshots")
    op.drop_index("ix_charts_saved_query_id", table_name="charts")
    op.drop_table("charts")
    op.drop_index("ix_saved_queries_connection_id", table_name="saved_queries")
    op.drop_table("saved_queries")
