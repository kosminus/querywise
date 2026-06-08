"""Data policies (Phase 4 — Milestone 3)

Revision ID: 011
Revises: 010
Create Date: 2026-06-08

Adds ``data_policies`` — governance rules enforced before a query reaches the
connector: role-scoped row/runtime caps, allow/block table lists, blocked
columns, PII column masking, and row-level filters. Connection-scoped like the
semantic layer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_policies",
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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column(
            "applies_to_roles", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("max_rows", sa.Integer, nullable=True),
        sa.Column("max_runtime_seconds", sa.Integer, nullable=True),
        sa.Column("allowed_tables", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocked_tables", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocked_columns", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("masked_columns", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("row_filters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_data_policies_connection_id", "data_policies", ["connection_id"])


def downgrade() -> None:
    op.drop_index("ix_data_policies_connection_id", table_name="data_policies")
    op.drop_table("data_policies")
