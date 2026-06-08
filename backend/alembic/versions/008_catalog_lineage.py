"""Catalog lineage (Phase 3 — Milestone 2)

Revision ID: 008
Revises: 007
Create Date: 2026-06-08

Adds ``artifact_dependencies`` — lineage edges recording which tables/columns a
saved query or metric references, parsed from its SQL via sqlglot. Powers the
catalog impact view ("what depends on this table") and the per-artifact
"what this touches" view. Names are stored denormalized; table_id/column_id are
resolved best-effort against the schema cache.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifact_dependencies",
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
        sa.Column("artifact_type", sa.String(20), nullable=False),
        sa.Column("artifact_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ref_kind", sa.String(10), nullable=False),
        sa.Column("schema_name", sa.String(255), nullable=True),
        sa.Column("table_name", sa.String(255), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=True),
        sa.Column(
            "table_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cached_tables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "column_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cached_columns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_artifact_dependencies_artifact",
        "artifact_dependencies",
        ["artifact_type", "artifact_id"],
    )
    op.create_index(
        "ix_artifact_dependencies_table",
        "artifact_dependencies",
        ["connection_id", "table_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_artifact_dependencies_table", table_name="artifact_dependencies")
    op.drop_index("ix_artifact_dependencies_artifact", table_name="artifact_dependencies")
    op.drop_table("artifact_dependencies")
