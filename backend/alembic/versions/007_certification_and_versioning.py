"""Certification + semantic versioning (Phase 3 — Milestone 1)

Revision ID: 007
Revises: 006
Create Date: 2026-06-08

Adds a trust/lifecycle layer to the semantic objects. Metrics, glossary terms,
sample queries, and saved queries gain a ``status``
(draft|in_review|certified|deprecated), an integer ``version``, and certification
stamps (``certified_by_id`` / ``certified_at``). The new ``semantic_versions``
table is an append-only changelog: a snapshot of an entity at each version with
the reviewer and reason, written on every content edit and status transition.

Existing rows default to status='draft', version=1 (saved_queries already carry
status + version from migration 005, so only the certification stamps are added
there).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables getting the full lifecycle column set (status + version + cert stamps).
_LIFECYCLE_TABLES = ("metric_definitions", "glossary_terms", "sample_queries")


def upgrade() -> None:
    for table in _LIFECYCLE_TABLES:
        op.add_column(
            table,
            sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        )
        op.add_column(
            table,
            sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        )
        op.add_column(
            table,
            sa.Column(
                "certified_by_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(
            table,
            sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        )

    # saved_queries already has status + version (migration 005); add cert stamps.
    op.add_column(
        "saved_queries",
        sa.Column(
            "certified_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "saved_queries",
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "semantic_versions",
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
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("change_reason", sa.Text, nullable=True),
        sa.Column(
            "changed_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_semantic_versions_entity",
        "semantic_versions",
        ["entity_type", "entity_id", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_versions_entity", table_name="semantic_versions")
    op.drop_table("semantic_versions")

    op.drop_column("saved_queries", "certified_at")
    op.drop_column("saved_queries", "certified_by_id")

    for table in _LIFECYCLE_TABLES:
        op.drop_column(table, "certified_at")
        op.drop_column(table, "certified_by_id")
        op.drop_column(table, "version")
        op.drop_column(table, "status")
