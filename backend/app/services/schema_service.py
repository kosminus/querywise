import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors.connector_registry import get_or_create_connector
from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError
from app.db.models.schema_cache import CachedColumn, CachedRelationship, CachedTable
from app.services.connection_service import get_connection, get_decrypted_connection_string


async def introspect_and_cache(
    db: AsyncSession,
    connection_id: uuid.UUID,
    ctx: AuthContext,
) -> dict[str, int]:
    """Introspect a target database and cache the schema metadata."""
    conn = await get_connection(db, connection_id, ctx, write=True)
    connection_string = get_decrypted_connection_string(conn)

    connector = await get_or_create_connector(
        str(connection_id), conn.connector_type, connection_string
    )

    # Clear existing cached data for this connection
    await db.execute(
        delete(CachedRelationship).where(CachedRelationship.connection_id == connection_id)
    )
    await db.execute(
        delete(CachedTable).where(CachedTable.connection_id == connection_id)
    )
    await db.flush()

    schemas = await connector.introspect_schemas()
    total_tables = 0
    total_columns = 0
    total_relationships = 0

    # Map of (schema, table_name) -> CachedTable for FK resolution
    table_map: dict[tuple[str, str], CachedTable] = {}

    for schema_name in schemas:
        tables = await connector.introspect_tables(schema_name)

        for table_info in tables:
            cached_table = CachedTable(
                connection_id=connection_id,
                schema_name=table_info.schema_name,
                table_name=table_info.table_name,
                table_type=table_info.table_type,
                comment=table_info.comment,
                row_count_estimate=table_info.row_count_estimate,
            )
            db.add(cached_table)
            await db.flush()  # Get the ID

            table_map[(schema_name, table_info.table_name)] = cached_table
            total_tables += 1

            for col_info in table_info.columns:
                cached_col = CachedColumn(
                    table_id=cached_table.id,
                    column_name=col_info.name,
                    data_type=col_info.data_type,
                    is_nullable=col_info.is_nullable,
                    is_primary_key=col_info.is_primary_key,
                    default_value=col_info.default_value,
                    comment=col_info.comment,
                    ordinal_position=col_info.ordinal_position,
                )
                db.add(cached_col)
                total_columns += 1

    await db.flush()

    # Now process foreign keys
    for schema_name in schemas:
        tables = await connector.introspect_tables(schema_name)
        for table_info in tables:
            source_table = table_map.get((schema_name, table_info.table_name))
            if not source_table:
                continue

            for fk in table_info.foreign_keys:
                target_table = table_map.get((fk.referred_schema, fk.referred_table))
                if not target_table:
                    continue

                rel = CachedRelationship(
                    connection_id=connection_id,
                    constraint_name=fk.constraint_name,
                    source_table_id=source_table.id,
                    source_column=fk.column_name,
                    target_table_id=target_table.id,
                    target_column=fk.referred_column,
                )
                db.add(rel)
                total_relationships += 1

    # Update last_introspected_at
    conn.last_introspected_at = datetime.now(UTC)
    await db.flush()

    return {
        "tables_found": total_tables,
        "columns_found": total_columns,
        "relationships_found": total_relationships,
    }


async def get_tables(
    db: AsyncSession, connection_id: uuid.UUID, ctx: AuthContext
) -> list[CachedTable]:
    # Access check (raises if the connection isn't in the caller's workspace).
    await get_connection(db, connection_id, ctx)
    result = await db.execute(
        select(CachedTable)
        .where(CachedTable.connection_id == connection_id)
        .options(selectinload(CachedTable.columns))
        .order_by(CachedTable.schema_name, CachedTable.table_name)
    )
    return list(result.scalars().all())


async def get_table_detail(
    db: AsyncSession, table_id: uuid.UUID, ctx: AuthContext
) -> CachedTable:
    result = await db.execute(
        select(CachedTable)
        .where(CachedTable.id == table_id)
        .options(
            selectinload(CachedTable.columns),
            selectinload(CachedTable.outgoing_relationships).selectinload(
                CachedRelationship.target_table
            ),
            selectinload(CachedTable.incoming_relationships).selectinload(
                CachedRelationship.source_table
            ),
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise NotFoundError("Table", str(table_id))
    # Ensure the table's connection belongs to the caller's workspace.
    await get_connection(db, table.connection_id, ctx)
    return table
