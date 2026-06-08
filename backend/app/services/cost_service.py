"""Cost & usage attribution (Phase 4 — Milestone 4).

``compute_cost`` turns connector-reported stats into a USD estimate using the
configured pricing. ``record_execution_cost`` writes one
:class:`CostAttribution` per execution — best-effort, never raising into the
query response (like audit). The aggregation helpers back the analytics API.

Cost is connector-specific and post-hoc: only BigQuery reports scanned bytes /
slot time today; other connectors fall back to the optional time-based estimate
(``COST_PER_SECOND_USD``, default 0).
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import AuthContext
from app.db.models.cost_attribution import CostAttribution
from app.db.models.query_history import QueryExecution
from app.services.lineage_service import REF_TABLE, dialect_for, extract_refs

logger = logging.getLogger("querywise")

_TIB = 1024**4


def compute_cost(stats: dict[str, Any] | None, execution_time_ms: float | None) -> float:
    """Estimate query cost (USD) from connector stats, else time-based fallback."""
    stats = stats or {}
    cost = 0.0
    scanned = stats.get("billed_bytes") or stats.get("scanned_bytes")
    if scanned:
        cost += (scanned / _TIB) * settings.cost_per_tib_scanned_usd
    if stats.get("slot_ms"):
        cost += stats["slot_ms"] * settings.cost_per_slot_ms_usd
    if stats.get("dbu"):
        cost += stats["dbu"] * settings.cost_per_dbu_usd
    if cost == 0.0 and execution_time_ms and settings.cost_per_second_usd:
        cost += (execution_time_ms / 1000.0) * settings.cost_per_second_usd
    return round(cost, 6)


def _referenced_tables(sql: str | None, connector_type: str | None) -> list[str]:
    if not sql:
        return []
    refs = extract_refs(sql, dialect_for(connector_type))
    return [
        f"{r.schema_name}.{r.table_name}" if r.schema_name else r.table_name
        for r in refs
        if r.ref_kind == REF_TABLE
    ]


async def record_execution_cost(
    db: AsyncSession,
    *,
    execution: QueryExecution,
    ctx: AuthContext,
    connector_type: str | None,
    stats: dict[str, Any] | None,
    final_sql: str | None,
) -> None:
    """Write a CostAttribution for one execution. Never raises."""
    try:
        stats = stats or {}
        attribution = CostAttribution(
            organization_id=execution.organization_id,
            workspace_id=ctx.workspace_id,
            connection_id=execution.connection_id,
            user_id=execution.user_id,
            query_execution_id=execution.id,
            source_provider=connector_type,
            status=execution.execution_status,
            execution_time_ms=execution.execution_time_ms,
            row_count=execution.row_count,
            scanned_bytes=stats.get("scanned_bytes") or stats.get("billed_bytes"),
            slot_ms=stats.get("slot_ms"),
            dbu=stats.get("dbu"),
            cost_usd=compute_cost(stats, execution.execution_time_ms),
            tables=_referenced_tables(final_sql, connector_type),
        )
        async with db.begin_nested():
            db.add(attribution)
    except Exception:  # noqa: BLE001 — cost capture must never break the query
        logger.warning("Failed to record cost attribution", exc_info=True)


# --------------------------------------------------------------------------- #
# Aggregations (org-scoped, admin-facing analytics)
# --------------------------------------------------------------------------- #
async def usage_summary(
    db: AsyncSession, organization_id: uuid.UUID, since: datetime
) -> dict[str, Any]:
    stmt = select(
        func.count().label("total"),
        func.coalesce(func.sum(case((CostAttribution.status == "error", 1), else_=0)), 0).label(
            "errors"
        ),
        func.coalesce(func.sum(CostAttribution.cost_usd), 0.0).label("cost"),
        func.coalesce(func.sum(CostAttribution.scanned_bytes), 0).label("scanned"),
        func.avg(CostAttribution.execution_time_ms).label("avg_ms"),
    ).where(
        CostAttribution.organization_id == organization_id,
        CostAttribution.created_at >= since,
    )
    row = (await db.execute(stmt)).one()
    total = row.total or 0
    errors = row.errors or 0
    return {
        "total_queries": total,
        "error_count": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "total_cost_usd": round(float(row.cost or 0.0), 6),
        "total_scanned_bytes": int(row.scanned or 0),
        "avg_execution_ms": round(float(row.avg_ms), 2) if row.avg_ms is not None else None,
    }


_DIMENSIONS = {
    "workspace": CostAttribution.workspace_id,
    "user": CostAttribution.user_id,
    "connection": CostAttribution.connection_id,
}


async def cost_by(
    db: AsyncSession, organization_id: uuid.UUID, dimension: str, since: datetime
) -> list[dict[str, Any]]:
    col = _DIMENSIONS.get(dimension)
    if col is None:
        raise ValueError(f"dimension must be one of {sorted(_DIMENSIONS)}")
    stmt = (
        select(
            col.label("key"),
            func.coalesce(func.sum(CostAttribution.cost_usd), 0.0).label("cost"),
            func.count().label("n"),
        )
        .where(
            CostAttribution.organization_id == organization_id,
            CostAttribution.created_at >= since,
        )
        .group_by(col)
        .order_by(func.sum(CostAttribution.cost_usd).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "key": str(r.key) if r.key else None,
            "cost_usd": round(float(r.cost or 0.0), 6),
            "query_count": r.n,
        }
        for r in rows
    ]


async def slowest_queries(
    db: AsyncSession, organization_id: uuid.UUID, since: datetime, limit: int = 10
) -> list[dict[str, Any]]:
    stmt = (
        select(
            CostAttribution.query_execution_id,
            CostAttribution.execution_time_ms,
            CostAttribution.cost_usd,
            CostAttribution.source_provider,
            QueryExecution.natural_language,
        )
        .join(QueryExecution, QueryExecution.id == CostAttribution.query_execution_id, isouter=True)
        .where(
            CostAttribution.organization_id == organization_id,
            CostAttribution.created_at >= since,
            CostAttribution.execution_time_ms.isnot(None),
        )
        .order_by(CostAttribution.execution_time_ms.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "query_execution_id": str(r.query_execution_id) if r.query_execution_id else None,
            "execution_time_ms": r.execution_time_ms,
            "cost_usd": round(float(r.cost_usd or 0.0), 6),
            "source_provider": r.source_provider,
            "question": r.natural_language,
        }
        for r in rows
    ]


async def most_queried_tables(
    db: AsyncSession, organization_id: uuid.UUID, since: datetime, limit: int = 10
) -> list[dict[str, Any]]:
    """Top referenced tables in the window (aggregated from the ``tables`` lists)."""
    stmt = select(CostAttribution.tables).where(
        CostAttribution.organization_id == organization_id,
        CostAttribution.created_at >= since,
    )
    counter: Counter[str] = Counter()
    for (tables,) in (await db.execute(stmt)).all():
        counter.update(tables or [])
    return [{"table": name, "query_count": n} for name, n in counter.most_common(limit)]
