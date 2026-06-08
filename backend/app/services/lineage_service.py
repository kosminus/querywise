"""Lineage extraction (Phase 3 — Milestone 2).

Parses an artifact's SQL with sqlglot to record which tables/columns it touches,
stored as :class:`ArtifactDependency` edges. Powers the catalog impact view
("what depends on this table") and the per-artifact "what this touches" view.

sqlglot is an optional dependency (the ``[lineage]`` extra). When it is absent,
extraction degrades to a no-op — the parent write (saving a query/metric) is never
blocked by lineage.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext
from app.db.models.artifact_dependency import (
    ARTIFACT_METRIC,
    ARTIFACT_SAVED_QUERY,
    REF_COLUMN,
    REF_TABLE,
    ArtifactDependency,
)
from app.db.models.connection import DatabaseConnection
from app.db.models.schema_cache import CachedColumn, CachedTable

logger = logging.getLogger(__name__)

# Map our connector types to sqlglot dialect names.
_DIALECTS: dict[str, str] = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "databricks": "databricks",
}


def dialect_for(connector_type: str | None) -> str | None:
    if not connector_type:
        return None
    return _DIALECTS.get(connector_type.lower())


@dataclass(frozen=True)
class Ref:
    """A table or column reference parsed out of SQL."""

    ref_kind: str  # REF_TABLE | REF_COLUMN
    schema_name: str | None
    table_name: str
    column_name: str | None = None


def extract_refs(sql: str, dialect: str | None = None) -> list[Ref]:
    """Extract table + qualified-column references from a SQL string.

    Returns an empty list if sqlglot is unavailable or the SQL cannot be parsed —
    lineage is best-effort and must never raise into the caller.
    """
    if not sql or not sql.strip():
        return []
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        logger.debug("sqlglot not installed; skipping lineage extraction")
        return []

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as exc:
        logger.debug("lineage parse failed: %s", exc)
        return []

    refs: dict[tuple, Ref] = {}

    # Table references, plus an alias -> table map for resolving qualified columns.
    alias_to_table: dict[str, tuple[str | None, str]] = {}
    for table in tree.find_all(exp.Table):
        table_name = table.name
        if not table_name:
            continue
        schema_name = table.db or None
        key: tuple = (REF_TABLE, schema_name, table_name, None)
        refs[key] = Ref(REF_TABLE, schema_name, table_name)
        alias_to_table[table_name] = (schema_name, table_name)
        if table.alias:
            alias_to_table[table.alias] = (schema_name, table_name)

    # Column references — only keep those we can attribute to a known table
    # (qualified by an alias/table name, or unambiguous single-table queries).
    single_table = (
        next(iter(alias_to_table.values())) if len(set(alias_to_table.values())) == 1 else None
    )
    for col in tree.find_all(exp.Column):
        col_name = col.name
        if not col_name or col_name == "*":
            continue
        qualifier = col.table
        if qualifier and qualifier in alias_to_table:
            schema_name, table_name = alias_to_table[qualifier]
        elif not qualifier and single_table is not None:
            schema_name, table_name = single_table
        else:
            continue
        key = (REF_COLUMN, schema_name, table_name, col_name)
        refs[key] = Ref(REF_COLUMN, schema_name, table_name, col_name)

    return list(refs.values())


async def _resolve_ids(
    db: AsyncSession, connection_id: uuid.UUID, ref: Ref
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Best-effort resolve a Ref's table_id / column_id against the schema cache."""
    table_stmt = select(CachedTable).where(
        CachedTable.connection_id == connection_id,
        CachedTable.table_name == ref.table_name,
    )
    if ref.schema_name:
        table_stmt = table_stmt.where(CachedTable.schema_name == ref.schema_name)
    table = (await db.execute(table_stmt.limit(1))).scalar_one_or_none()
    if table is None:
        return None, None
    if ref.ref_kind == REF_TABLE or not ref.column_name:
        return table.id, None
    column = (
        await db.execute(
            select(CachedColumn)
            .where(
                CachedColumn.table_id == table.id,
                CachedColumn.column_name == ref.column_name,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return table.id, (column.id if column else None)


async def recompute_for_artifact(
    db: AsyncSession,
    ctx: AuthContext,
    artifact_type: str,
    artifact_id: uuid.UUID,
    sql: str,
    connection_id: uuid.UUID,
    *,
    connector_type: str | None = None,
) -> int:
    """Re-derive an artifact's lineage edges from its SQL. Best-effort; never raises.

    Returns the number of edges written (0 on parse failure / missing sqlglot).
    """
    try:
        refs = extract_refs(sql, dialect_for(connector_type))
        # Replace prior edges for this artifact.
        existing = await db.execute(
            select(ArtifactDependency).where(
                ArtifactDependency.artifact_type == artifact_type,
                ArtifactDependency.artifact_id == artifact_id,
            )
        )
        for row in existing.scalars().all():
            await db.delete(row)

        for ref in refs:
            table_id, column_id = await _resolve_ids(db, connection_id, ref)
            db.add(
                ArtifactDependency(
                    organization_id=ctx.organization_id,
                    connection_id=connection_id,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    ref_kind=ref.ref_kind,
                    schema_name=ref.schema_name,
                    table_name=ref.table_name,
                    column_name=ref.column_name,
                    table_id=table_id,
                    column_id=column_id,
                )
            )
        await db.flush()
        return len(refs)
    except Exception:
        logger.exception("lineage recompute failed for %s %s", artifact_type, artifact_id)
        return 0


async def _connector_type(db: AsyncSession, connection_id: uuid.UUID) -> str | None:
    return (
        await db.execute(
            select(DatabaseConnection.connector_type).where(DatabaseConnection.id == connection_id)
        )
    ).scalar_one_or_none()


async def recompute_saved_query(db: AsyncSession, ctx: AuthContext, saved) -> int:
    """Re-derive lineage for a saved query from its pinned SQL (best-effort)."""
    connector_type = await _connector_type(db, saved.connection_id)
    return await recompute_for_artifact(
        db,
        ctx,
        ARTIFACT_SAVED_QUERY,
        saved.id,
        saved.pinned_sql,
        saved.connection_id,
        connector_type=connector_type,
    )


async def recompute_metric(db: AsyncSession, ctx: AuthContext, metric) -> int:
    """Re-derive lineage for a metric from its SQL expression (best-effort)."""
    connector_type = await _connector_type(db, metric.connection_id)
    return await recompute_for_artifact(
        db,
        ctx,
        ARTIFACT_METRIC,
        metric.id,
        metric.sql_expression,
        metric.connection_id,
        connector_type=connector_type,
    )


async def refs_for_artifact(
    db: AsyncSession, artifact_type: str, artifact_id: uuid.UUID
) -> list[ArtifactDependency]:
    """What this artifact touches."""
    result = await db.execute(
        select(ArtifactDependency)
        .where(
            ArtifactDependency.artifact_type == artifact_type,
            ArtifactDependency.artifact_id == artifact_id,
        )
        .order_by(ArtifactDependency.table_name, ArtifactDependency.column_name)
    )
    return list(result.scalars().all())


async def dependents_of(
    db: AsyncSession,
    connection_id: uuid.UUID,
    table_name: str,
    column_name: str | None = None,
) -> list[ArtifactDependency]:
    """What artifacts depend on a given table (optionally a specific column)."""
    stmt = select(ArtifactDependency).where(
        ArtifactDependency.connection_id == connection_id,
        ArtifactDependency.table_name == table_name,
    )
    if column_name:
        stmt = stmt.where(ArtifactDependency.column_name == column_name)
    result = await db.execute(stmt.order_by(ArtifactDependency.artifact_type))
    return list(result.scalars().all())
