"""Semantic layer compiler — service layer.

Orchestrates the engine in ``app/semantic_compiler/`` as a background job,
persists findings for review, and dispatches accepted findings into the real
semantic objects through the existing creation paths (embedding + lineage).

Findings never touch the semantic tables until accepted: draft metrics and
glossary terms are retrieved by the query-pipeline context builder, so
unreviewed compiler output must stay out of them.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.connectors.connector_registry import get_or_create_connector
from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError
from app.db.models.compilation import CompilationFinding, CompilationRun
from app.db.models.data_policy import DataPolicy
from app.db.models.dictionary import DictionaryEntry
from app.db.models.glossary import GlossaryTerm
from app.db.models.metric import MetricDefinition
from app.db.models.schema_cache import CachedColumn, CachedRelationship, CachedTable
from app.db.session import async_session_factory
from app.jobs import get_job_queue, register_job
from app.semantic_compiler import CompilerInput, Thresholds, run_compiler
from app.semantic_compiler.collectors import (
    build_table_profiles,
    collect_pg_stats,
    collect_query_logs,
    collect_view_definitions,
)
from app.services import compilation_progress as progress
from app.services.connection_service import get_connection, get_decrypted_connection_string
from app.services.lineage_service import dialect_for

logger = logging.getLogger(__name__)

# Merged "refusal boundary" policies created on accept (one per connection).
PII_POLICY_NAME = "Compiler: PII masking"
DEAD_TABLE_POLICY_NAME = "Compiler: dead tables"

_RUN_STAGES = 6  # introspect, statistics, views, query logs, inference, annotate/persist


class ConnectorProber:
    """Adapts a BaseConnector to the engine's narrow Prober protocol."""

    def __init__(self, connector: Any):
        self._connector = connector

    async def query(self, sql: str, max_rows: int = 1000) -> list[dict[str, Any]]:
        result = await self._connector.execute_query(sql, timeout_seconds=15, max_rows=max_rows)
        return [dict(zip(result.columns, row, strict=False)) for row in result.rows]

    async def sample_values(
        self, schema: str, table: str, column: str, limit: int = 20
    ) -> list[Any]:
        return await self._connector.get_sample_values(schema, table, column, limit)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


async def start_run(
    db: AsyncSession,
    connection_id: uuid.UUID,
    ctx: AuthContext,
    options: dict[str, Any] | None = None,
) -> CompilationRun:
    """Create a queued run and launch the background job."""
    await get_connection(db, connection_id, ctx, write=True)
    if progress.is_running(str(connection_id)):
        raise ValueError("A compilation is already running for this connection")

    run = CompilationRun(
        connection_id=connection_id,
        status="queued",
        options=options or {},
        triggered_by_id=ctx.user_id,
    )
    db.add(run)
    await db.flush()
    await db.commit()

    queue = get_job_queue()
    task = queue.submit("semantic_compilation", run.id, name=f"compile-{connection_id}")
    if queue.backend_name == "inprocess" and isinstance(task, asyncio.Task):
        progress.register_task(str(connection_id), task)
    return run


async def _run_compilation_job(run_id: uuid.UUID) -> None:
    """Background job: collect evidence, run inference, annotate, persist findings."""
    async with async_session_factory() as db:
        run = await db.get(CompilationRun, run_id)
        if run is None:
            logger.warning("compilation run %s vanished before starting", run_id)
            return
        cid = str(run.connection_id)
        progress.start_tracking(cid, _RUN_STAGES)
        run.status = "running"
        run.started_at = datetime.now(UTC)
        await db.commit()
        try:
            await _execute_run(db, run)
            run.status = "completed"
            run.finished_at = datetime.now(UTC)
            await db.commit()
            progress.mark_completed(cid)
        except Exception as exc:
            await db.rollback()
            run = await db.get(CompilationRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.finished_at = datetime.now(UTC)
                await db.commit()
            progress.mark_failed(cid, str(exc))
            logger.exception("compilation run %s failed", run_id)


async def _execute_run(db: AsyncSession, run: CompilationRun) -> None:
    from app.services.identity_service import system_context

    ctx = await system_context(db)
    conn = await get_connection(db, run.connection_id, ctx)
    connector = await get_or_create_connector(
        str(run.connection_id), conn.connector_type, get_decrypted_connection_string(conn)
    )
    prober = ConnectorProber(connector)
    cid = str(run.connection_id)
    options = run.options or {}
    is_postgres = conn.connector_type.lower() == "postgresql"

    # --- collect ---
    progress.advance(cid, "Introspecting schema")
    table_infos = []
    for schema in await connector.introspect_schemas():
        table_infos.extend(await connector.introspect_tables(schema))
    tables = build_table_profiles(table_infos)

    progress.advance(cid, "Reading column statistics")
    stats_available = await collect_pg_stats(prober, tables) if is_postgres else False

    progress.advance(cid, "Reading view definitions")
    views, views_available = await collect_view_definitions(prober) if is_postgres else ([], False)

    progress.advance(cid, "Reading query logs")
    logged, logs_available = await collect_query_logs(prober) if is_postgres else ([], False)

    sources = {
        "pg_stats": stats_available,
        "views": views_available,
        "query_logs": logs_available,
    }

    # --- infer ---
    progress.advance(cid, "Running inference")
    thresholds = Thresholds()
    if "min_confidence" in options:
        thresholds.min_confidence = float(options["min_confidence"])
    inp = CompilerInput(
        dialect=dialect_for(conn.connector_type),
        tables=tables,
        views=views,
        logged_queries=logged,
        sources_available=sources,
        options={"ignore_declared_fks": bool(options.get("ignore_declared_fks"))},
    )
    findings = await run_compiler(inp, prober, thresholds)

    # --- annotate (optional) + persist ---
    progress.advance(cid, "Annotating and saving findings")
    if options.get("llm_enabled", True):
        findings = await _annotate(findings)

    # A new run supersedes prior un-reviewed proposals; accepted/dismissed
    # findings are review history (and the rematerialization source) — untouched.
    stale = await db.execute(
        select(CompilationFinding).where(
            CompilationFinding.connection_id == run.connection_id,
            CompilationFinding.status == "proposed",
        )
    )
    superseded = 0
    for old in stale.scalars():
        old.status = "dismissed"
        old.reviewed_at = datetime.now(UTC)
        superseded += 1

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
        db.add(
            CompilationFinding(
                run_id=run.id,
                connection_id=run.connection_id,
                kind=finding.kind,
                title=finding.title[:255],
                payload=finding.payload,
                evidence=[e.as_dict() for e in finding.evidence],
                confidence=round(finding.confidence, 3),
            )
        )
    run.stats = {
        "findings": counts,
        "sources_available": sources,
        "superseded_proposals": superseded,
        "tables_examined": len(tables),
        "views_examined": len(views),
        "logged_queries_examined": len(logged),
    }


async def _annotate(findings: list) -> list:
    """LLM naming pass — merged onto naming fields only, never structure.

    Best-effort: returns the findings unchanged if the provider is unavailable.
    """
    from app.llm.agents.semantic_annotator import SemanticAnnotatorAgent
    from app.llm.base_provider import LLMConfig
    from app.llm.prompts.annotator_prompts import KIND_FIELDS
    from app.llm.provider_registry import get_provider

    try:
        provider = get_provider(settings.default_llm_provider)
    except Exception as exc:
        logger.warning("annotation skipped — provider unavailable: %s", exc)
        return findings
    model = (
        settings.ollama_model
        if settings.default_llm_provider == "ollama"
        else settings.default_llm_model
    )
    agent = SemanticAnnotatorAgent(provider, LLMConfig(model=model, max_tokens=4096))

    by_kind: dict[str, list[int]] = {}
    for i, finding in enumerate(findings):
        if finding.kind in KIND_FIELDS:
            by_kind.setdefault(finding.kind, []).append(i)

    for kind, indices in by_kind.items():
        payloads = [
            {
                "title": findings[i].title,
                "payload": findings[i].payload,
                "evidence": [e.as_dict() for e in findings[i].evidence],
            }
            for i in indices
        ]
        annotations = await agent.annotate(kind, payloads)
        for local_index, fields in annotations.items():
            if 0 <= local_index < len(indices):
                findings[indices[local_index]].payload.update(fields)
    return findings


register_job("semantic_compilation", _run_compilation_job)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_runs(
    db: AsyncSession, connection_id: uuid.UUID, ctx: AuthContext
) -> list[CompilationRun]:
    await get_connection(db, connection_id, ctx)
    result = await db.execute(
        select(CompilationRun)
        .where(CompilationRun.connection_id == connection_id)
        .order_by(CompilationRun.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


async def get_run(db: AsyncSession, run_id: uuid.UUID, ctx: AuthContext) -> CompilationRun:
    run = await db.get(CompilationRun, run_id)
    if run is None:
        raise NotFoundError("CompilationRun", str(run_id))
    await get_connection(db, run.connection_id, ctx)
    return run


async def list_findings(
    db: AsyncSession,
    connection_id: uuid.UUID,
    ctx: AuthContext,
    status: str | None = None,
    kind: str | None = None,
) -> list[CompilationFinding]:
    await get_connection(db, connection_id, ctx)
    stmt = select(CompilationFinding).where(CompilationFinding.connection_id == connection_id)
    if status:
        stmt = stmt.where(CompilationFinding.status == status)
    if kind:
        stmt = stmt.where(CompilationFinding.kind == kind)
    stmt = stmt.order_by(CompilationFinding.kind, CompilationFinding.confidence.desc()).limit(500)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Review: accept / dismiss
# ---------------------------------------------------------------------------


async def _get_finding(
    db: AsyncSession, finding_id: uuid.UUID, ctx: AuthContext
) -> CompilationFinding:
    finding = await db.get(CompilationFinding, finding_id)
    if finding is None:
        raise NotFoundError("CompilationFinding", str(finding_id))
    await get_connection(db, finding.connection_id, ctx, write=True)
    return finding


async def dismiss_finding(
    db: AsyncSession, finding_id: uuid.UUID, ctx: AuthContext
) -> CompilationFinding:
    finding = await _get_finding(db, finding_id, ctx)
    if finding.status != "proposed":
        raise ValueError(f"Finding already {finding.status}")
    finding.status = "dismissed"
    finding.reviewed_by_id = ctx.user_id
    finding.reviewed_at = datetime.now(UTC)
    await db.flush()
    return finding


async def accept_finding(
    db: AsyncSession, finding_id: uuid.UUID, ctx: AuthContext
) -> CompilationFinding:
    """Materialize a finding as a real semantic object (status stays 'draft' there)."""
    finding = await _get_finding(db, finding_id, ctx)
    if finding.status != "proposed":
        raise ValueError(f"Finding already {finding.status}")

    handler = _ACCEPT_HANDLERS.get(finding.kind)
    if handler is None:
        raise ValueError(f"Unknown finding kind: {finding.kind}")
    entity_type, entity_id = await handler(db, finding, ctx)

    finding.status = "accepted"
    finding.created_entity_type = entity_type
    finding.created_entity_id = entity_id
    finding.reviewed_by_id = ctx.user_id
    finding.reviewed_at = datetime.now(UTC)
    await db.flush()
    return finding


async def bulk_review(
    db: AsyncSession, finding_ids: list[uuid.UUID], action: str, ctx: AuthContext
) -> dict[str, int]:
    succeeded, failed = 0, 0
    for finding_id in finding_ids:
        try:
            if action == "accept":
                await accept_finding(db, finding_id, ctx)
            else:
                await dismiss_finding(db, finding_id, ctx)
            succeeded += 1
        except Exception as exc:
            logger.warning("bulk %s failed for finding %s: %s", action, finding_id, exc)
            failed += 1
    return {"succeeded": succeeded, "failed": failed}


# --- accept dispatch, one handler per kind ---------------------------------


async def _resolve_table(
    db: AsyncSession, connection_id: uuid.UUID, schema: str | None, table: str
) -> CachedTable | None:
    stmt = select(CachedTable).where(
        CachedTable.connection_id == connection_id, CachedTable.table_name == table
    )
    if schema:
        stmt = stmt.where(CachedTable.schema_name == schema)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def _resolve_column(
    db: AsyncSession, connection_id: uuid.UUID, schema: str | None, table: str, column: str
) -> CachedColumn | None:
    cached_table = await _resolve_table(db, connection_id, schema, table)
    if cached_table is None:
        return None
    stmt = select(CachedColumn).where(
        CachedColumn.table_id == cached_table.id, CachedColumn.column_name == column
    )
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def _create_relationship(
    db: AsyncSession,
    connection_id: uuid.UUID,
    payload: dict,
    confidence: float,
    evidence: list,
) -> CachedRelationship | None:
    source = await _resolve_table(
        db, connection_id, payload.get("source_schema"), payload["source_table"]
    )
    target = await _resolve_table(
        db, connection_id, payload.get("target_schema"), payload["target_table"]
    )
    if source is None or target is None:
        return None
    existing = await db.execute(
        select(CachedRelationship).where(
            CachedRelationship.connection_id == connection_id,
            CachedRelationship.source_table_id == source.id,
            CachedRelationship.source_column == payload["source_column"],
            CachedRelationship.target_table_id == target.id,
            CachedRelationship.target_column == payload["target_column"],
        )
    )
    found = existing.scalars().first()
    if found is not None:
        return found
    rel = CachedRelationship(
        connection_id=connection_id,
        constraint_name=None,
        origin="inferred",
        confidence=confidence,
        cardinality=payload.get("cardinality"),
        evidence=evidence,
        source_table_id=source.id,
        source_column=payload["source_column"],
        target_table_id=target.id,
        target_column=payload["target_column"],
    )
    db.add(rel)
    await db.flush()
    return rel


async def _accept_relationship(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    rel = await _create_relationship(
        db, finding.connection_id, finding.payload, finding.confidence, finding.evidence
    )
    if rel is None:
        raise ValueError("Source or target table not found in schema cache — re-introspect first")
    return "relationship", rel.id


async def _accept_metric(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    from app.services.embedding_service import embed_metric
    from app.services.lineage_service import recompute_metric

    p = finding.payload
    metric = MetricDefinition(
        connection_id=finding.connection_id,
        organization_id=ctx.organization_id,
        created_by_id=ctx.user_id,
        metric_name=p["metric_name"],
        display_name=p.get("display_name") or p["metric_name"].replace("_", " ").title(),
        description=p.get("description"),
        sql_expression=p["sql_expression"],
        aggregation_type=p.get("aggregation_type"),
        related_tables=p.get("related_tables") or [],
        dimensions=p.get("dimensions") or [],
        filters=p.get("filters") or {},
    )
    db.add(metric)
    await db.flush()
    try:
        metric.metric_embedding = await embed_metric(metric)
    except Exception as exc:
        logger.warning("metric embedding deferred (provider unavailable): %s", exc)
    try:
        await recompute_metric(db, ctx, metric)
    except Exception as exc:
        logger.warning("metric lineage recompute failed: %s", exc)
    return "metric", metric.id


async def _accept_glossary(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    from app.services.embedding_service import embed_glossary_term

    p = finding.payload
    term = GlossaryTerm(
        connection_id=finding.connection_id,
        organization_id=ctx.organization_id,
        created_by_id=ctx.user_id,
        term=p["term"],
        definition=p["definition"],
        sql_expression=p.get("sql_expression") or p["term"],
        related_tables=p.get("related_tables") or [],
        related_columns=p.get("related_columns") or [],
        examples=p.get("examples") or [],
    )
    db.add(term)
    await db.flush()
    try:
        term.term_embedding = await embed_glossary_term(term)
    except Exception as exc:
        logger.warning("glossary embedding deferred (provider unavailable): %s", exc)
    return "glossary", term.id


async def _create_dictionary_entries(
    db: AsyncSession, connection_id: uuid.UUID, payload: dict
) -> CachedColumn | None:
    column = await _resolve_column(
        db, connection_id, payload.get("schema"), payload["table"], payload["column"]
    )
    if column is None:
        return None
    existing = await db.execute(
        select(DictionaryEntry).where(DictionaryEntry.column_id == column.id).limit(1)
    )
    if existing.scalars().first() is not None:
        return column  # entries already present — don't duplicate
    for entry in payload.get("entries", []):
        db.add(
            DictionaryEntry(
                column_id=column.id,
                raw_value=str(entry["raw_value"])[:255],
                display_value=str(entry.get("display_value") or entry["raw_value"])[:255],
                description=entry.get("description"),
                sort_order=int(entry.get("sort_order") or 0),
            )
        )
    await db.flush()
    return column


async def _accept_dictionary(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    column = await _create_dictionary_entries(db, finding.connection_id, finding.payload)
    if column is None:
        raise ValueError("Column not found in schema cache — re-introspect first")
    return "dictionary_column", column.id


async def _get_or_create_merged_policy(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext, name: str
) -> DataPolicy:
    result = await db.execute(
        select(DataPolicy).where(
            DataPolicy.connection_id == finding.connection_id, DataPolicy.name == name
        )
    )
    policy = result.scalars().first()
    if policy is None:
        # Created DISABLED: policies have no draft status and enforce live —
        # the reviewer flips `enabled` after checking the contents.
        policy = DataPolicy(
            connection_id=finding.connection_id,
            organization_id=ctx.organization_id,
            name=name,
            enabled=False,
        )
        db.add(policy)
        await db.flush()
    return policy


async def _accept_masking(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    policy = await _get_or_create_merged_policy(db, finding, ctx, PII_POLICY_NAME)
    masked = finding.payload["masked_column"]
    if masked not in (policy.masked_columns or []):
        policy.masked_columns = [*(policy.masked_columns or []), masked]
    await db.flush()
    return "data_policy", policy.id


async def _accept_dead_table(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    policy = await _get_or_create_merged_policy(db, finding, ctx, DEAD_TABLE_POLICY_NAME)
    table = finding.payload["table"]
    if table not in (policy.blocked_tables or []):
        policy.blocked_tables = [*(policy.blocked_tables or []), table]
    await db.flush()
    return "data_policy", policy.id


async def _accept_row_filter(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    p = finding.payload
    policy = DataPolicy(
        connection_id=finding.connection_id,
        organization_id=ctx.organization_id,
        name=f"Compiler: row filter on {p['column']}",
        enabled=False,  # the :tenant_id placeholder must be edited first
        row_filters=p.get("row_filters") or {},
    )
    db.add(policy)
    await db.flush()
    return "data_policy", policy.id


async def _accept_fanout(
    db: AsyncSession, finding: CompilationFinding, ctx: AuthContext
) -> tuple[str, uuid.UUID]:
    """Fan-out guidance lands as a knowledge document — the knowledge resolver
    already injects relevant chunks into the SQL-generation prompt."""
    from app.services.knowledge_service import import_document

    p = finding.payload
    body = p.get("description") or ""
    content = (
        f"{p['guidance']}\n\n{body}\n\n"
        f"Join: {p['child_table']}.{p['join']['child_column']} = "
        f"{p['parent_table']}.{p['join']['parent_column']} (N:1). "
        f"Measure columns at risk on {p['parent_table']}: "
        f"{', '.join(p.get('risky_columns', []))}."
    ).strip()
    doc = await import_document(
        db,
        connection_id=finding.connection_id,
        title=f"Join guidance: {p['parent_table']} joined to {p['child_table']}",
        content=content,
        organization_id=ctx.organization_id,
        source_url=None,
    )
    return "knowledge", doc.id


_ACCEPT_HANDLERS = {
    "relationship": _accept_relationship,
    "metric": _accept_metric,
    "glossary": _accept_glossary,
    "dictionary": _accept_dictionary,
    "data_policy_masking": _accept_masking,
    "data_policy_row_filter": _accept_row_filter,
    "dead_table": _accept_dead_table,
    "fanout_warning": _accept_fanout,
}


# ---------------------------------------------------------------------------
# Rematerialization after re-introspection
# ---------------------------------------------------------------------------


async def rematerialize_accepted(db: AsyncSession, connection_id: uuid.UUID) -> dict[str, int]:
    """Re-create cache-anchored artifacts from accepted findings.

    ``introspect_and_cache`` wipes all cached tables (cascading to inferred
    relationships and dictionary entries). Accepted findings are name-keyed,
    so they can be resolved against the fresh cache and re-created.
    """
    result = await db.execute(
        select(CompilationFinding).where(
            CompilationFinding.connection_id == connection_id,
            CompilationFinding.status == "accepted",
            CompilationFinding.kind.in_(["relationship", "dictionary"]),
        )
    )
    relationships = 0
    dictionaries = 0
    for finding in result.scalars():
        try:
            if finding.kind == "relationship":
                rel = await _create_relationship(
                    db, connection_id, finding.payload, finding.confidence, finding.evidence
                )
                if rel is not None:
                    relationships += 1
            else:
                column = await _create_dictionary_entries(db, connection_id, finding.payload)
                if column is not None:
                    dictionaries += 1
        except Exception as exc:
            logger.warning("rematerialization failed for finding %s: %s", finding.id, exc)
    await db.flush()
    return {"relationships": relationships, "dictionary_columns": dictionaries}
