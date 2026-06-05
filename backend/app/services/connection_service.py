import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.connector_registry import (
    get_connector_class,
    get_or_create_connector,
    remove_connector,
)
from app.core.auth import AuthContext
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.secrets import get_secrets_provider
from app.db.models.connection import DatabaseConnection
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR

# Encryption of connection strings is delegated to the configured secrets
# backend (env/Fernet by default — see app.core.secrets).


def _encrypt(value: str) -> str:
    return get_secrets_provider().encrypt(value)


def _decrypt(value: str) -> str:
    return get_secrets_provider().decrypt(value)


def _assert_access(conn: DatabaseConnection, ctx: AuthContext, *, write: bool = False) -> None:
    """Enforce workspace scoping + role for a connection.

    Cross-workspace access raises 404 (don't leak existence); private
    connections are visible only to their owner or a workspace admin.
    """
    if conn.organization_id != ctx.organization_id or conn.workspace_id != ctx.workspace_id:
        raise NotFoundError("Connection", str(conn.id))
    if conn.is_private and conn.owner_id != ctx.user_id and not ctx.has_role(ROLE_ADMIN):
        raise AuthorizationError("This connection is private to its owner.")
    if write:
        ctx.require_role(ROLE_EDITOR)


async def list_connections(db: AsyncSession, ctx: AuthContext) -> list[DatabaseConnection]:
    stmt = (
        select(DatabaseConnection)
        .where(
            DatabaseConnection.organization_id == ctx.organization_id,
            DatabaseConnection.workspace_id == ctx.workspace_id,
        )
        .order_by(DatabaseConnection.created_at.desc())
    )
    # Non-admins don't see other people's private connections.
    if not ctx.has_role(ROLE_ADMIN):
        stmt = stmt.where(
            or_(
                DatabaseConnection.is_private.is_(False),
                DatabaseConnection.owner_id == ctx.user_id,
            )
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_connection(
    db: AsyncSession,
    connection_id: uuid.UUID,
    ctx: AuthContext,
    *,
    write: bool = False,
) -> DatabaseConnection:
    conn = await db.get(DatabaseConnection, connection_id)
    if not conn:
        raise NotFoundError("Connection", str(connection_id))
    _assert_access(conn, ctx, write=write)
    return conn


async def create_connection(
    db: AsyncSession,
    ctx: AuthContext,
    name: str,
    connector_type: str,
    connection_string: str,
    default_schema: str = "public",
    max_query_timeout_seconds: int = 30,
    max_rows: int = 1000,
    is_private: bool = False,
) -> DatabaseConnection:
    ctx.require_role(ROLE_EDITOR)
    # Validate connector type exists
    get_connector_class(connector_type)

    conn = DatabaseConnection(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        owner_id=ctx.user_id,
        is_private=is_private,
        name=name,
        connector_type=connector_type,
        connection_string_encrypted=_encrypt(connection_string),
        default_schema=default_schema,
        max_query_timeout_seconds=max_query_timeout_seconds,
        max_rows=max_rows,
    )
    db.add(conn)
    await db.flush()
    return conn


async def update_connection(
    db: AsyncSession,
    connection_id: uuid.UUID,
    ctx: AuthContext,
    **updates: object,
) -> DatabaseConnection:
    conn = await get_connection(db, connection_id, ctx, write=True)

    if "connection_string" in updates and updates["connection_string"] is not None:
        conn.connection_string_encrypted = _encrypt(str(updates.pop("connection_string")))

    for key, value in updates.items():
        if value is not None and hasattr(conn, key):
            setattr(conn, key, value)

    await db.flush()
    # Invalidate cached connector since config may have changed
    await remove_connector(str(connection_id))
    return conn


async def delete_connection(
    db: AsyncSession, connection_id: uuid.UUID, ctx: AuthContext
) -> None:
    conn = await get_connection(db, connection_id, ctx, write=True)
    await remove_connector(str(connection_id))
    await db.delete(conn)
    await db.flush()


async def test_connection(
    db: AsyncSession, connection_id: uuid.UUID, ctx: AuthContext
) -> tuple[bool, str]:
    conn = await get_connection(db, connection_id, ctx)
    connection_string = _decrypt(conn.connection_string_encrypted)
    try:
        connector = await get_or_create_connector(
            str(connection_id), conn.connector_type, connection_string
        )
        success = await connector.test_connection()
        return (success, "Connection successful" if success else "Connection test failed")
    except Exception as e:
        return (False, str(e))


def get_decrypted_connection_string(conn: DatabaseConnection) -> str:
    return _decrypt(conn.connection_string_encrypted)
