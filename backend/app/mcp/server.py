"""FastMCP server exposing QueryWise to MCP clients (Claude, etc.).

Mounted on the FastAPI app under /mcp via streamable HTTP. Reuses the
existing services so tools share the same behavior as the REST API.

Tools fall into four groups:
  * Connections — list / create / test / introspect / delete.
  * Schema      — list_tables, describe_table (needed when wiring metrics).
  * Semantic    — CRUD over glossary, metrics, dictionary, knowledge,
                  sample queries.
  * Query       — get_semantic_context, generate_sql, run_sql, ask,
                  query_history.

The 'connection' argument is a name or id (case-insensitive).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.connection import DatabaseConnection
from app.db.models.dictionary import DictionaryEntry
from app.db.models.glossary import GlossaryTerm
from app.db.models.knowledge import KnowledgeDocument
from app.db.models.metric import MetricDefinition
from app.db.models.query_history import QueryExecution
from app.db.models.sample_query import SampleQuery
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.db.session import async_session_factory
from app.semantic.context_builder import build_context
from app.services import connection_service, query_service, schema_service
from app.services.embedding_service import (
    embed_glossary_term,
    embed_metric,
    embed_sample_query,
)
from app.services.knowledge_service import import_document
from app.services.setup_service import launch_background_embeddings

# --------------------------------------------------------------------------- #
# DB session helper
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def _session_scope() -> AsyncIterator[AsyncSession]:
    """Mirror of `get_db` — commits on success, rolls back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --------------------------------------------------------------------------- #
# Shared parameter descriptors / annotation presets
# --------------------------------------------------------------------------- #

_CONN_DESC = (
    "Target database connection — its name or id (case-insensitive). "
    "List the available connections with list_connections."
)
Connection = Annotated[str, Field(description=_CONN_DESC)]

_READ_ONLY = dict(readOnlyHint=True)
_READ_ONLY_EXTERNAL = dict(readOnlyHint=True, openWorldHint=True)
_WRITE = dict(readOnlyHint=False, idempotentHint=False)
_DESTRUCTIVE = dict(readOnlyHint=False, destructiveHint=True, idempotentHint=True)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _resolve_connection(db: AsyncSession, connection: str) -> DatabaseConnection:
    """Resolve a connection by id (preferred) or by name (case-insensitive)."""
    try:
        cid = uuid.UUID(str(connection))
        conn = await db.get(DatabaseConnection, cid)
        if conn:
            return conn
    except (ValueError, TypeError):
        pass

    name = str(connection).strip()
    result = await db.execute(
        select(DatabaseConnection).where(
            func.lower(DatabaseConnection.name) == name.lower()
        )
    )
    conn = result.scalars().first()
    if not conn:
        # List the actual connection names inline. Some MCP clients drop
        # list_connections from their tool-search and would otherwise loop
        # guessing names; seeing the options here lets them self-correct.
        available = (await db.execute(select(DatabaseConnection.name))).scalars().all()
        options = ", ".join(repr(n) for n in available) if available else "none configured"
        raise ValueError(
            f"No connection matching '{connection}'. Available connections: {options}."
        )
    return conn


async def _resolve_column_id(
    db: AsyncSession,
    connection_id: uuid.UUID,
    table_name: str,
    column_name: str,
) -> uuid.UUID | None:
    """Find a cached column id by (connection, table_name, column_name)."""
    result = await db.execute(
        select(CachedColumn.id)
        .join(CachedTable, CachedColumn.table_id == CachedTable.id)
        .where(
            CachedTable.connection_id == connection_id,
            func.lower(CachedTable.table_name) == table_name.lower(),
            func.lower(CachedColumn.column_name) == column_name.lower(),
        )
    )
    return result.scalar_one_or_none()


def _conn_dict(c: DatabaseConnection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "connector_type": c.connector_type,
        "default_schema": c.default_schema,
        "max_rows": c.max_rows,
        "max_query_timeout_seconds": c.max_query_timeout_seconds,
        "last_introspected_at": (
            c.last_introspected_at.isoformat()
            if isinstance(c.last_introspected_at, datetime)
            else None
        ),
    }


def _format_ask_result(res: dict[str, Any], max_preview_rows: int = 20) -> str:
    """Render the dict returned by ``query_service.execute_nl_query`` as Markdown."""
    out: list[str] = [
        "### Answer Summary",
        res.get("summary") or "No natural-language summary generated.",
    ]

    highlights = res.get("highlights") or []
    if highlights:
        out.append("\n### Highlights")
        out.extend(f"- {hl}" for hl in highlights)

    out += [
        "\n### Executed SQL",
        f"```sql\n{res.get('final_sql') or res.get('generated_sql') or ''}\n```",
        "\n### Metadata",
        f"- Execution time: {(res.get('execution_time_ms') or 0):.2f} ms",
        f"- Row count: {res.get('row_count', 0)}",
        f"- LLM: {res.get('llm_provider')} ({res.get('llm_model')})",
        f"- Retries: {res.get('retry_count', 0)}",
    ]

    rows = res.get("rows") or []
    cols = res.get("columns") or []
    if rows:
        out.append(f"\n### Data preview (top {max_preview_rows} rows)")
        header = " | ".join(str(c) for c in cols)
        out.append(header)
        out.append("-" * max(3, len(header)))
        for r in rows[:max_preview_rows]:
            out.append(" | ".join("NULL" if v is None else str(v) for v in r))
        if len(rows) > max_preview_rows:
            out.append(f"... and {len(rows) - max_preview_rows} more rows (truncated)")

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# FastMCP instance
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def _mcp_lifespan(_server: FastMCP) -> AsyncIterator[dict]:
    """Startup for standalone modes (stdio / direct HTTP via mcp.run).

    HTTP-mount mode bypasses this — FastAPI's own lifespan already runs
    ensure_embedding_dimensions and auto_setup_sample_db. Starlette does
    not invoke mounted-app lifespans, which is exactly the behavior we
    want here.
    """
    from app.services.setup_service import ensure_embedding_dimensions

    await ensure_embedding_dimensions()
    yield {}


mcp = FastMCP(
    "querywise",
    instructions=(
        "Query databases in natural language through a business semantic layer. "
        "Recommended loop for a question: call get_semantic_context(connection, "
        "question) to assemble grounded schema + glossary + metric + example "
        "context, write a read-only SELECT, then call run_sql(connection, sql). "
        "Use ask() to delegate the whole NL->SQL pipeline to the server. Manage "
        "the semantic layer with the glossary/metric/dictionary/knowledge tools. "
        "'connection' accepts a connection name or id."
    ),
    # We mount the streamable-HTTP app at /mcp on the FastAPI router, so the
    # path inside the mounted app stays at "/" — otherwise URLs would be
    # /mcp/mcp.
    streamable_http_path="/",
    lifespan=_mcp_lifespan,
)


# --------------------------------------------------------------------------- #
# Connections
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List connections", **_READ_ONLY))
async def list_connections() -> list[dict]:
    """List configured database connections (id, name, type, limits)."""
    async with _session_scope() as db:
        conns = await connection_service.list_connections(db)
        return [_conn_dict(c) for c in conns]


@mcp.tool(annotations=ToolAnnotations(title="Create connection", **_WRITE))
async def create_connection(
    name: Annotated[
        str,
        Field(description="Unique, human-friendly name used to reference this connection later."),
    ],
    connector_type: Annotated[
        str,
        Field(description="One of: postgresql, bigquery, databricks."),
    ],
    connection_string: Annotated[
        str,
        Field(
            description="Driver URL (PostgreSQL) or connector-specific JSON config "
            "(BigQuery/Databricks). Stored encrypted at rest."
        ),
    ],
    default_schema: Annotated[
        str,
        Field(description="Default schema to introspect and query when none is specified."),
    ] = "public",
    max_rows: Annotated[
        int,
        Field(description="Maximum number of rows any query on this connection may return."),
    ] = 1000,
    max_query_timeout_seconds: Annotated[
        int,
        Field(description="Per-query timeout, in seconds."),
    ] = 30,
) -> dict:
    """Register a new target database connection.

    Stores credentials encrypted at rest. Does NOT verify connectivity — follow
    with test_connection, then introspect_connection. Returns the new id.
    """
    async with _session_scope() as db:
        conn = await connection_service.create_connection(
            db,
            name=name,
            connector_type=connector_type,
            connection_string=connection_string,
            default_schema=default_schema,
            max_rows=max_rows,
            max_query_timeout_seconds=max_query_timeout_seconds,
        )
        return _conn_dict(conn)


@mcp.tool(annotations=ToolAnnotations(title="Test connection", **_READ_ONLY_EXTERNAL))
async def test_connection(connection: Connection) -> dict:
    """Check that a connection can be reached and authenticated."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        ok, message = await connection_service.test_connection(db, conn.id)
        return {"success": ok, "message": message}


@mcp.tool(
    annotations=ToolAnnotations(
        title="Introspect connection",
        readOnlyHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def introspect_connection(
    connection: Connection,
    generate_embeddings: Annotated[
        bool,
        Field(
            description="Also build vector embeddings for semantic schema search. "
            "Needs an embedding provider; otherwise keyword matching is used."
        ),
    ] = True,
) -> dict:
    """Read the target database's structure and cache it.

    Run once per connection before querying, and again after schema changes.
    Idempotent — re-running refreshes the cache.
    """
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        cid = conn.id
        counts = await schema_service.introspect_and_cache(db, cid)
    if generate_embeddings:
        launch_background_embeddings(cid)
    return {**counts, "embeddings_started": bool(generate_embeddings)}


@mcp.tool(annotations=ToolAnnotations(title="Delete connection", **_DESTRUCTIVE))
async def delete_connection(connection: Connection) -> dict:
    """Permanently delete a connection and all its cached schema + semantic metadata."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        await connection_service.delete_connection(db, conn.id)
        return {"deleted": True}


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List tables", **_READ_ONLY))
async def list_tables(connection: Connection) -> list[dict]:
    """List a connection's cached tables with their columns."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        tables = await schema_service.get_tables(db, conn.id)
        return [
            {
                "id": str(t.id),
                "schema": t.schema_name,
                "name": t.table_name,
                "type": t.table_type,
                "comment": t.comment,
                "row_count_estimate": t.row_count_estimate,
                "columns": [
                    {
                        "name": col.column_name,
                        "type": col.data_type,
                        "nullable": col.is_nullable,
                        "primary_key": col.is_primary_key,
                        "comment": col.comment,
                    }
                    for col in sorted(t.columns, key=lambda c: c.ordinal_position)
                ],
            }
            for t in tables
        ]


@mcp.tool(annotations=ToolAnnotations(title="Describe table", **_READ_ONLY))
async def describe_table(
    connection: Connection,
    table_name: Annotated[
        str, Field(description="Exact table name to describe, as shown by list_tables.")
    ],
) -> dict:
    """Describe one cached table in detail, including its foreign keys."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        tables = await schema_service.get_tables(db, conn.id)
        match = next((t for t in tables if t.table_name == table_name), None)
        if not match:
            raise ValueError(f"Table '{table_name}' not found on '{conn.name}'.")
        detail = await schema_service.get_table_detail(db, match.id)
        return {
            "schema": detail.schema_name,
            "name": detail.table_name,
            "comment": detail.comment,
            "columns": [
                {
                    "name": c.column_name,
                    "type": c.data_type,
                    "nullable": c.is_nullable,
                    "primary_key": c.is_primary_key,
                    "default": c.default_value,
                    "comment": c.comment,
                }
                for c in sorted(detail.columns, key=lambda c: c.ordinal_position)
            ],
            "foreign_keys": [
                {
                    "column": r.source_column,
                    "references_table": r.target_table.table_name,
                    "references_column": r.target_column,
                }
                for r in detail.outgoing_relationships
            ],
            "referenced_by": [
                {
                    "table": r.source_table.table_name,
                    "column": r.source_column,
                    "references_column": r.target_column,
                }
                for r in detail.incoming_relationships
            ],
        }


# --------------------------------------------------------------------------- #
# Core query tools
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="Get semantic context", **_READ_ONLY))
async def get_semantic_context(
    connection: Connection,
    question: Annotated[
        str,
        Field(
            description="The NL question; used to select the most relevant schema "
            "and semantic-layer entries."
        ),
    ],
) -> str:
    """Assemble grounded, SQL-ready context for a question.

    Returns the relevant tables/columns, foreign keys, business glossary, metric
    definitions, value dictionaries, knowledge excerpts, and example queries as
    formatted text. Pair with run_sql to keep the LLM key on the client side.
    """
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        ctx = await build_context(db, conn.id, question, dialect=conn.connector_type)
        return ctx.prompt_context


@mcp.tool(annotations=ToolAnnotations(title="Run SQL", **_READ_ONLY_EXTERNAL))
async def run_sql(
    connection: Connection,
    sql: Annotated[
        str,
        Field(
            description="A single read-only SELECT to execute. Non-SELECT or unsafe "
            "SQL is rejected."
        ),
    ],
) -> dict:
    """Execute read-only SQL against the target database and return the rows."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        result = await query_service.execute_raw_sql(db, conn.id, sql)
        return {
            "columns": result.get("columns"),
            "rows": result.get("rows"),
            "row_count": result.get("row_count"),
            "truncated": result.get("truncated"),
            "execution_time_ms": result.get("execution_time_ms"),
        }


@mcp.tool(annotations=ToolAnnotations(title="Generate SQL", **_READ_ONLY_EXTERNAL))
async def generate_sql(
    connection: Connection,
    question: Annotated[str, Field(description="NL question to translate into SQL.")],
) -> dict:
    """Translate a natural-language question into SQL without executing it."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        return await query_service.generate_sql_only(db, conn.id, question)


@mcp.tool(annotations=ToolAnnotations(title="Ask (NL->answer)", **_READ_ONLY_EXTERNAL))
async def ask(
    connection: Connection,
    question: Annotated[str, Field(description="NL question to answer end-to-end.")],
) -> str:
    """Answer a natural-language question end-to-end via the server pipeline.

    Builds context, generates SQL, validates, executes, and interprets the
    results. Returns Markdown.
    """
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        res = await query_service.execute_nl_query(db, conn.id, question)
        return _format_ask_result(res)


@mcp.tool(annotations=ToolAnnotations(title="Query history", **_READ_ONLY))
async def query_history(
    connection: Connection,
    limit: Annotated[
        int, Field(description="Maximum number of past executions to return (newest first).")
    ] = 20,
) -> list[dict]:
    """List recent query executions for a connection, newest first."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        res = await db.execute(
            select(QueryExecution)
            .where(QueryExecution.connection_id == conn.id)
            .order_by(desc(QueryExecution.created_at))
            .limit(limit)
        )
        return [
            {
                "id": str(q.id),
                "question": q.natural_language,
                "sql": q.final_sql,
                "status": q.execution_status,
                "row_count": q.row_count,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in res.scalars().all()
        ]


# --------------------------------------------------------------------------- #
# Glossary
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List glossary terms", **_READ_ONLY))
async def list_glossary(connection: Connection) -> list[dict]:
    """List the business glossary terms defined for a connection."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        result = await db.execute(
            select(GlossaryTerm)
            .where(GlossaryTerm.connection_id == conn.id)
            .order_by(GlossaryTerm.term)
        )
        return [
            {
                "id": str(t.id),
                "term": t.term,
                "definition": t.definition,
                "sql_expression": t.sql_expression,
                "related_tables": t.related_tables or [],
            }
            for t in result.scalars().all()
        ]


@mcp.tool(annotations=ToolAnnotations(title="Add glossary term", **_WRITE))
async def add_glossary_term(
    connection: Connection,
    term: Annotated[
        str, Field(description="The business term being defined (e.g. 'active customer').")
    ],
    definition: Annotated[str, Field(description="Plain-language meaning of the term.")],
    sql_expression: Annotated[
        str,
        Field(description="SQL snippet/predicate that implements the term."),
    ],
    related_tables: Annotated[
        list[str] | None,
        Field(description="Optional list of table names the term applies to."),
    ] = None,
) -> dict:
    """Define a business glossary term that maps business language to a SQL expression."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        obj = GlossaryTerm(
            connection_id=conn.id,
            term=term,
            definition=definition,
            sql_expression=sql_expression,
            related_tables=related_tables or [],
        )
        db.add(obj)
        await db.flush()
        try:
            obj.term_embedding = await embed_glossary_term(obj)
        except Exception:
            pass
        return {"id": str(obj.id), "term": obj.term}


@mcp.tool(annotations=ToolAnnotations(title="Delete glossary term", **_DESTRUCTIVE))
async def delete_glossary_term(
    term_id: Annotated[
        str, Field(description="Id of the glossary term to delete (from list_glossary).")
    ],
) -> dict:
    """Delete one business glossary term by its id."""
    async with _session_scope() as db:
        obj = await db.get(GlossaryTerm, uuid.UUID(term_id))
        if not obj:
            return {"deleted": False}
        await db.delete(obj)
        return {"deleted": True}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List metrics", **_READ_ONLY))
async def list_metrics(connection: Connection) -> list[dict]:
    """List the metric definitions for a connection."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        result = await db.execute(
            select(MetricDefinition)
            .where(MetricDefinition.connection_id == conn.id)
            .order_by(MetricDefinition.display_name)
        )
        return [
            {
                "id": str(m.id),
                "metric_name": m.metric_name,
                "display_name": m.display_name,
                "description": m.description,
                "sql_expression": m.sql_expression,
                "aggregation_type": m.aggregation_type,
                "related_tables": m.related_tables or [],
                "dimensions": m.dimensions or [],
            }
            for m in result.scalars().all()
        ]


@mcp.tool(annotations=ToolAnnotations(title="Add metric", **_WRITE))
async def add_metric(
    connection: Connection,
    metric_name: Annotated[
        str, Field(description="Machine-friendly metric identifier (e.g. 'gross_revenue').")
    ],
    display_name: Annotated[
        str, Field(description="Human-friendly metric label (e.g. 'Gross Revenue').")
    ],
    sql_expression: Annotated[
        str,
        Field(
            description="SQL aggregate expression that produces the metric "
            "(e.g. 'SUM(amount)')."
        ),
    ],
    description: Annotated[
        str | None,
        Field(description="Optional plain-language description of what the metric measures."),
    ] = None,
    aggregation_type: Annotated[
        str | None,
        Field(description="Optional aggregation hint (e.g. 'sum', 'avg', 'count')."),
    ] = None,
    related_tables: Annotated[
        list[str] | None,
        Field(description="Optional list of table names the metric is computed over."),
    ] = None,
    dimensions: Annotated[
        list[str] | None,
        Field(description="Optional list of dimensions (column names) the metric is sliced by."),
    ] = None,
) -> dict:
    """Define a named, reusable KPI (e.g. 'gross_revenue = SUM(amount)').

    Use add_glossary_term for phrase-to-SQL mappings; use this for aggregate KPIs.
    """
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        obj = MetricDefinition(
            connection_id=conn.id,
            metric_name=metric_name,
            display_name=display_name,
            sql_expression=sql_expression,
            description=description,
            aggregation_type=aggregation_type,
            related_tables=related_tables or [],
            dimensions=dimensions or [],
        )
        db.add(obj)
        await db.flush()
        try:
            obj.metric_embedding = await embed_metric(obj)
        except Exception:
            pass
        return {
            "id": str(obj.id),
            "metric_name": obj.metric_name,
            "display_name": obj.display_name,
        }


@mcp.tool(annotations=ToolAnnotations(title="Delete metric", **_DESTRUCTIVE))
async def delete_metric(
    metric_id: Annotated[
        str, Field(description="Id of the metric to delete (from list_metrics).")
    ],
) -> dict:
    """Delete one metric definition by its id."""
    async with _session_scope() as db:
        obj = await db.get(MetricDefinition, uuid.UUID(metric_id))
        if not obj:
            return {"deleted": False}
        await db.delete(obj)
        return {"deleted": True}


# --------------------------------------------------------------------------- #
# Dictionary
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="Add dictionary entry", **_WRITE))
async def add_dictionary_entry(
    connection: Connection,
    table_name: Annotated[
        str, Field(description="Table containing the column (must already be introspected).")
    ],
    column_name: Annotated[
        str, Field(description="Column whose coded value you are explaining.")
    ],
    raw_value: Annotated[
        str,
        Field(description="The stored/coded value as it appears in the column (e.g. '1')."),
    ],
    display_value: Annotated[
        str,
        Field(description="The business meaning of that value (e.g. 'Performing')."),
    ],
    description: Annotated[
        str | None,
        Field(description="Optional extra explanation of the value."),
    ] = None,
) -> dict:
    """Map a coded column value to its business meaning (e.g. stage '1' -> 'Performing')."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        col_id = await _resolve_column_id(db, conn.id, table_name, column_name)
        if not col_id:
            raise ValueError(
                f"Column {table_name}.{column_name} not found "
                "(introspect the connection first)."
            )
        obj = DictionaryEntry(
            column_id=col_id,
            raw_value=raw_value,
            display_value=display_value,
            description=description,
        )
        db.add(obj)
        await db.flush()
        return {"id": str(obj.id), "raw_value": obj.raw_value}


# --------------------------------------------------------------------------- #
# Sample queries
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List sample queries", **_READ_ONLY))
async def list_sample_queries(connection: Connection) -> list[dict]:
    """List saved example NL -> SQL pairs (used as few-shot examples)."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        result = await db.execute(
            select(SampleQuery)
            .where(SampleQuery.connection_id == conn.id)
            .order_by(SampleQuery.created_at.desc())
        )
        return [
            {
                "id": str(s.id),
                "natural_language": s.natural_language,
                "sql_query": s.sql_query,
                "is_validated": s.is_validated,
                "tags": s.tags or [],
            }
            for s in result.scalars().all()
        ]


@mcp.tool(annotations=ToolAnnotations(title="Add sample query", **_WRITE))
async def add_sample_query(
    connection: Connection,
    natural_language: Annotated[
        str, Field(description="The example natural-language question.")
    ],
    sql_query: Annotated[
        str, Field(description="The validated SQL that answers the question.")
    ],
    description: Annotated[
        str | None, Field(description="Optional description / comment.")
    ] = None,
    tags: Annotated[
        list[str] | None, Field(description="Optional tags for filtering.")
    ] = None,
    is_validated: Annotated[
        bool, Field(description="Whether the SQL has been validated to run correctly.")
    ] = True,
) -> dict:
    """Save an NL -> SQL example pair used as a few-shot to steer generation."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        obj = SampleQuery(
            connection_id=conn.id,
            natural_language=natural_language,
            sql_query=sql_query,
            description=description,
            tags=tags or [],
            is_validated=is_validated,
        )
        db.add(obj)
        await db.flush()
        try:
            obj.question_embedding = await embed_sample_query(obj)
        except Exception:
            pass
        return {"id": str(obj.id)}


# --------------------------------------------------------------------------- #
# Knowledge
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=ToolAnnotations(title="List knowledge documents", **_READ_ONLY))
async def list_knowledge(connection: Connection) -> list[dict]:
    """List knowledge documents attached to a connection."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        result = await db.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.connection_id == conn.id)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        return [
            {
                "id": str(d.id),
                "title": d.title,
                "source_url": d.source_url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in result.scalars().all()
        ]


@mcp.tool(annotations=ToolAnnotations(title="Add knowledge document", **_WRITE))
async def add_knowledge(
    connection: Connection,
    title: Annotated[str, Field(description="Human-readable title of the document.")],
    content: Annotated[
        str,
        Field(
            description="Document body (plain text or HTML — HTML is auto-detected and "
            "cleaned). Will be chunked and embedded."
        ),
    ],
    source_url: Annotated[
        str | None,
        Field(description="Optional source URL for provenance."),
    ] = None,
) -> dict:
    """Import a knowledge document (text or HTML). Chunked and embedded for retrieval."""
    async with _session_scope() as db:
        conn = await _resolve_connection(db, connection)
        doc = await import_document(
            db,
            connection_id=conn.id,
            title=title,
            content=content,
            source_url=source_url,
        )
        return {"id": str(doc.id), "title": doc.title}


@mcp.tool(annotations=ToolAnnotations(title="Delete knowledge document", **_DESTRUCTIVE))
async def delete_knowledge(
    doc_id: Annotated[
        str, Field(description="Id of the knowledge document to delete (from list_knowledge).")
    ],
) -> dict:
    """Delete a knowledge document and all its chunks."""
    async with _session_scope() as db:
        result = await db.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == uuid.UUID(doc_id))
            .options(selectinload(KnowledgeDocument.chunks))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return {"deleted": False}
        await db.delete(doc)
        return {"deleted": True}


# --------------------------------------------------------------------------- #
# Mount helper — used by main.py to attach the streamable-HTTP app to FastAPI.
# --------------------------------------------------------------------------- #


def mount_mcp(app, path: str = "/mcp") -> None:
    """Mount the FastMCP streamable-HTTP app onto a FastAPI instance.

    Also installs the MCP session manager into the FastAPI lifespan so the
    underlying task group runs for the lifetime of the app.
    """
    mcp_app = mcp.streamable_http_app()
    app.mount(path, mcp_app)

    # Chain the MCP session manager into the existing FastAPI lifespan.
    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(scope_app):
        async with mcp.session_manager.run():
            async with existing_lifespan(scope_app):
                yield

    app.router.lifespan_context = combined_lifespan
