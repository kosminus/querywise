"""Dashboards and tiles (Phase 2 — Milestone 2)

Revision ID: 006
Revises: 005
Create Date: 2026-06-08

Adds workspace-scoped dashboards and their tiles. A dashboard composes saved
queries (from any connection in the workspace) into a draggable grid; tiles
render a saved query as a chart or table, and dashboard-level filters flow into
each tile's run via the saved-query parameter system.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
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
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("filters", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dashboards_workspace_id", "dashboards", ["workspace_id"])

    op.create_table(
        "dashboard_tiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dashboard_id",
            UUID(as_uuid=True),
            sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_query_id",
            UUID(as_uuid=True),
            sa.ForeignKey("saved_queries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chart_id",
            UUID(as_uuid=True),
            sa.ForeignKey("charts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("position", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("refresh_interval", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dashboard_tiles_dashboard_id", "dashboard_tiles", ["dashboard_id"])


def downgrade() -> None:
    op.drop_index("ix_dashboard_tiles_dashboard_id", table_name="dashboard_tiles")
    op.drop_table("dashboard_tiles")
    op.drop_index("ix_dashboards_workspace_id", table_name="dashboards")
    op.drop_table("dashboards")
