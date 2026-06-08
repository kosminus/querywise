"""Saved-query service — parameter rendering, result caching, re-runs.

Re-running a saved query renders its typed parameters into the pinned SQL and
goes through :func:`query_service.execute_raw_sql`, which already enforces the
read-only SQL safety blocklist, executes via the connector, and records history.
Results are persisted as :class:`ResultSnapshot` rows which double as the cache.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import AuthContext
from app.core.exceptions import AppError
from app.db.models.result_snapshot import ResultSnapshot
from app.db.models.saved_query import SavedQuery
from app.services import query_service

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class ParamError(AppError):
    """Raised when supplied parameters are missing, unknown, or ill-typed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


def _render_value(name: str, ptype: str, value: Any) -> str:
    """Render a single parameter as a safe SQL literal.

    Numbers/booleans are validated and inlined bare; strings/dates are validated
    and emitted as single-quoted literals with embedded quotes doubled. The
    rendered SQL is still run through ``check_sql_safety`` downstream, so this is
    defense-in-depth against breaking out of a literal — not the only guard.
    """
    if ptype == "number":
        if isinstance(value, bool):
            raise ParamError(f"Parameter '{name}' must be a number.")
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise ParamError(f"Parameter '{name}' must be a number.") from exc
        if num != num or num in (float("inf"), float("-inf")):
            raise ParamError(f"Parameter '{name}' must be a finite number.")
        # Preserve integers without a trailing .0
        rendered = int(num) if num.is_integer() else num
        return str(rendered)

    if ptype == "boolean":
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return "TRUE" if value.strip().lower() == "true" else "FALSE"
        raise ParamError(f"Parameter '{name}' must be a boolean.")

    if ptype == "date":
        if isinstance(value, (date, datetime)):
            iso = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
        else:
            try:
                iso = date.fromisoformat(str(value)).isoformat()
            except ValueError as exc:
                raise ParamError(f"Parameter '{name}' must be a date (YYYY-MM-DD).") from exc
        return f"'{iso}'"

    # string (default)
    text = str(value).replace("\x00", "")
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def render_sql(
    pinned_sql: str,
    param_defs: list[dict] | None,
    supplied: dict[str, Any] | None,
) -> str:
    """Substitute ``{{name}}`` placeholders with type-safe SQL literals."""
    defs = {d["name"]: d for d in (param_defs or [])}
    supplied = supplied or {}

    placeholders = set(_PLACEHOLDER_RE.findall(pinned_sql))
    unknown = placeholders - set(defs)
    if unknown:
        raise ParamError(f"SQL references undefined parameter(s): {', '.join(sorted(unknown))}.")

    rendered: dict[str, str] = {}
    for name, d in defs.items():
        if name not in placeholders:
            continue
        if name in supplied and supplied[name] is not None:
            value = supplied[name]
        elif d.get("default") is not None:
            value = d["default"]
        else:
            raise ParamError(f"Missing required parameter '{name}'.")
        rendered[name] = _render_value(name, d.get("type", "string"), value)

    return _PLACEHOLDER_RE.sub(lambda m: rendered[m.group(1)], pinned_sql)


def compute_sql_hash(final_sql: str, params_used: dict[str, Any], connection_id: uuid.UUID) -> str:
    payload = "|".join(
        [
            final_sql,
            json.dumps(params_used, sort_keys=True, default=str),
            str(connection_id),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _latest_fresh_snapshot(db: AsyncSession, sql_hash: str) -> ResultSnapshot | None:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.result_cache_ttl_seconds)
    result = await db.execute(
        select(ResultSnapshot)
        .where(ResultSnapshot.sql_hash == sql_hash, ResultSnapshot.taken_at >= cutoff)
        .order_by(ResultSnapshot.taken_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_saved_query(
    db: AsyncSession,
    saved: SavedQuery,
    ctx: AuthContext,
    supplied_params: dict[str, Any] | None = None,
    *,
    refresh: bool = False,
) -> dict:
    """Run a saved query (cache-first) and return a run-result dict.

    Returns the same fields as the query pipeline plus ``cached`` and ``taken_at``.
    """
    supplied_params = supplied_params or {}
    final_sql = render_sql(saved.pinned_sql, saved.params, supplied_params)
    sql_hash = compute_sql_hash(final_sql, supplied_params, saved.connection_id)

    if not refresh:
        snap = await _latest_fresh_snapshot(db, sql_hash)
        if snap is not None:
            return {
                "columns": snap.columns or [],
                "column_types": snap.column_types or [],
                "rows": snap.rows or [],
                "row_count": snap.row_count or 0,
                "truncated": snap.truncated,
                "execution_time_ms": snap.execution_time_ms,
                "cached": True,
                "taken_at": snap.taken_at,
            }

    # Cache miss (or forced refresh): execute and persist a fresh snapshot.
    result = await query_service.execute_raw_sql(
        db,
        saved.connection_id,
        final_sql,
        ctx,
        original_question=saved.nl_question or saved.name,
    )

    snapshot = ResultSnapshot(
        organization_id=ctx.organization_id,
        connection_id=saved.connection_id,
        saved_query_id=saved.id,
        sql_hash=sql_hash,
        columns=result["columns"],
        column_types=result["column_types"],
        rows=result["rows"],
        row_count=result["row_count"],
        params_used=supplied_params,
        execution_time_ms=result["execution_time_ms"],
        truncated=result["truncated"],
    )
    db.add(snapshot)
    await db.flush()

    return {
        "columns": result["columns"],
        "column_types": result["column_types"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "execution_time_ms": result["execution_time_ms"],
        "cached": False,
        "taken_at": snapshot.taken_at,
    }
