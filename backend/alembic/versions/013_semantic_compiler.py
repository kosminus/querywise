"""Semantic layer compiler (Slice 1)

Revision ID: 013
Revises: 012
Create Date: 2026-06-10

Adds the compiler staging tables and inferred-relationship support:

* ``cached_relationships`` gains ``origin`` ('fk' | 'inferred'), ``confidence``,
  ``cardinality`` and ``evidence`` so join edges inferred by the compiler can
  coexist with FK-derived ones.
* ``compilation_runs`` — one row per compiler execution against a connection.
* ``compilation_findings`` — proposed semantic objects with name-keyed payloads,
  evidence, and confidence. Findings become real semantic objects only on
  explicit accept; accepted findings are the durable source for rematerializing
  inferred relationships and dictionary entries after re-introspection (which
  wipes the schema cache).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cached_relationships",
        sa.Column("origin", sa.String(20), nullable=False, server_default="fk"),
    )
    op.add_column("cached_relationships", sa.Column("confidence", sa.Float, nullable=True))
    op.add_column("cached_relationships", sa.Column("cardinality", sa.String(10), nullable=True))
    op.add_column("cached_relationships", sa.Column("evidence", JSONB, nullable=True))

    op.create_table(
        "compilation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("options", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "triggered_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_compilation_runs_connection_id", "compilation_runs", ["connection_id"])

    op.create_table(
        "compilation_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("compilation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.Float, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("created_entity_type", sa.String(40), nullable=True),
        sa.Column("created_entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "reviewed_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_compilation_findings_conn_status_kind",
        "compilation_findings",
        ["connection_id", "status", "kind"],
    )
    op.create_index("ix_compilation_findings_run_id", "compilation_findings", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_compilation_findings_run_id", table_name="compilation_findings")
    op.drop_index("ix_compilation_findings_conn_status_kind", table_name="compilation_findings")
    op.drop_table("compilation_findings")
    op.drop_index("ix_compilation_runs_connection_id", table_name="compilation_runs")
    op.drop_table("compilation_runs")
    op.drop_column("cached_relationships", "evidence")
    op.drop_column("cached_relationships", "cardinality")
    op.drop_column("cached_relationships", "confidence")
    op.drop_column("cached_relationships", "origin")
