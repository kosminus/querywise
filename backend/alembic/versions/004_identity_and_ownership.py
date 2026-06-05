"""Identity, teams & ownership (Phase 1)

Revision ID: 004
Revises: 003
Create Date: 2026-06-05

Adds the identity layer (organizations, users, teams, memberships, api_keys),
re-keys all core tables with organization_id, scopes connections to a workspace
(team) + owner, and promotes the free-text created_by / user_id columns to real
User foreign keys.

Migration strategy per the roadmap: add nullable → create the default org /
workspace / admin → backfill every existing row → enforce NOT NULL. Rollback is
``DISABLE_AUTH=true`` + this downgrade (+ pg_dump restore if needed).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.config import settings

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Core tables that gain organization_id (SaaS-ready scoping).
ORG_SCOPED_TABLES = [
    "database_connections",
    "glossary_terms",
    "metric_definitions",
    "sample_queries",
    "knowledge_documents",
    "query_executions",
]
# Tables whose free-text created_by becomes a created_by_id User FK.
CREATED_BY_TABLES = ["glossary_terms", "metric_definitions", "sample_queries"]


def _q(value: str) -> str:
    """Single-quote-escape a trusted config string for inline SQL."""
    return value.replace("'", "''")


def upgrade() -> None:
    org_slug = _q(settings.default_org_slug)
    admin_email = _q(settings.default_admin_email)

    # --- Identity tables ---------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("settings", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("sso_subject", sa.String(255), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("permissions", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Seed the default org / workspace / admin --------------------------
    op.execute(
        f"INSERT INTO organizations (name, slug) "
        f"VALUES ('{_q(settings.default_org_name)}', '{org_slug}')"
    )
    op.execute(
        f"INSERT INTO teams (organization_id, name, slug) "
        f"SELECT id, '{_q(settings.default_workspace_name)}', 'default-workspace' "
        f"FROM organizations WHERE slug = '{org_slug}'"
    )
    op.execute(
        f"INSERT INTO users (email, name, status) "
        f"VALUES ('{admin_email}', 'Administrator', 'active')"
    )
    op.execute(
        f"INSERT INTO memberships (user_id, team_id, role) "
        f"SELECT u.id, t.id, 'admin' FROM users u, teams t "
        f"JOIN organizations o ON o.id = t.organization_id "
        f"WHERE u.email = '{admin_email}' AND o.slug = '{org_slug}'"
    )

    org_subq = f"(SELECT id FROM organizations WHERE slug = '{org_slug}')"
    team_subq = (
        f"(SELECT t.id FROM teams t JOIN organizations o ON o.id = t.organization_id "
        f"WHERE o.slug = '{org_slug}' ORDER BY t.created_at LIMIT 1)"
    )
    admin_subq = f"(SELECT id FROM users WHERE email = '{admin_email}')"

    # --- organization_id on every core table -------------------------------
    for table in ORG_SCOPED_TABLES:
        op.add_column(table, sa.Column("organization_id", UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET organization_id = {org_subq}")
        op.alter_column(table, "organization_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_org_created", table, ["organization_id", "created_at"])

    # --- database_connections: workspace + owner + privacy -----------------
    op.add_column("database_connections", sa.Column("workspace_id", UUID(as_uuid=True), nullable=True))
    op.add_column("database_connections", sa.Column("owner_id", UUID(as_uuid=True), nullable=True))
    op.add_column(
        "database_connections",
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        f"UPDATE database_connections SET workspace_id = {team_subq}, owner_id = {admin_subq}"
    )
    op.alter_column("database_connections", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_database_connections_workspace_id",
        "database_connections",
        "teams",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_database_connections_owner_id",
        "database_connections",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- created_by → created_by_id User FK --------------------------------
    for table in CREATED_BY_TABLES:
        op.add_column(table, sa.Column("created_by_id", UUID(as_uuid=True), nullable=True))
        # Existing rows were created by the system; attribute them to the admin.
        op.execute(f"UPDATE {table} SET created_by_id = {admin_subq} WHERE created_by IS NOT NULL")
        op.create_foreign_key(
            f"fk_{table}_created_by_id",
            table,
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.drop_column(table, "created_by")

    # --- query_executions.user_id: free-text string → User FK --------------
    # Old free-text values cannot be mapped to real users; they become NULL.
    op.drop_column("query_executions", "user_id")
    op.add_column("query_executions", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_query_executions_user_id",
        "query_executions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # query_executions.user_id back to free-text
    op.drop_constraint("fk_query_executions_user_id", "query_executions", type_="foreignkey")
    op.drop_column("query_executions", "user_id")
    op.add_column("query_executions", sa.Column("user_id", sa.String(255), nullable=True))

    # created_by_id → created_by string
    for table in CREATED_BY_TABLES:
        op.drop_constraint(f"fk_{table}_created_by_id", table, type_="foreignkey")
        op.drop_column(table, "created_by_id")
        op.add_column(table, sa.Column("created_by", sa.String(255), nullable=True))

    # database_connections extras
    op.drop_constraint("fk_database_connections_owner_id", "database_connections", type_="foreignkey")
    op.drop_constraint(
        "fk_database_connections_workspace_id", "database_connections", type_="foreignkey"
    )
    op.drop_column("database_connections", "is_private")
    op.drop_column("database_connections", "owner_id")
    op.drop_column("database_connections", "workspace_id")

    # organization_id on core tables
    for table in ORG_SCOPED_TABLES:
        op.drop_index(f"ix_{table}_org_created", table_name=table)
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")

    # Identity tables
    op.drop_table("api_keys")
    op.drop_table("memberships")
    op.drop_table("teams")
    op.drop_table("users")
    op.drop_table("organizations")
