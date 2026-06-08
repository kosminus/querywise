"""Data-policy resolution + enforcement (Phase 4 — Milestone 3).

Policies are enforced in the query pipeline *before* the SQL reaches the
connector. ``resolve_effective`` merges every applicable policy into one
most-restrictive :class:`EffectivePolicy`; ``enforce_sql`` then blocks or
rewrites the SQL; ``mask_result`` redacts PII columns in the returned rows.

Security stance — **fail closed**. SQL-level rules (allow/block tables, blocked
columns, row filters) need sqlglot to analyze the query. If sqlglot is absent or
the SQL can't be parsed, those rules raise :class:`PolicyViolationError` rather than
letting the query through unfiltered. Row caps and column masking don't need
sqlglot and always apply.

Known boundary: blocked-column checks see only *explicitly referenced* columns —
``SELECT *`` is not expanded against the schema. PII protection under ``SELECT *``
is therefore the job of ``masked_columns`` (post-execution redaction), which is
star-safe.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError
from app.db.models.connection import DatabaseConnection
from app.db.models.data_policy import DataPolicy
from app.db.models.membership import ROLE_EDITOR
from app.services import audit_service

logger = logging.getLogger("querywise")

MASK_TOKEN = "***"


class PolicyViolationError(Exception):
    """Raised when a data policy blocks a query. ``reason`` is user-facing."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _norm(name: str) -> str:
    return str(name).strip().lower()


def _fqtn(schema: str | None, name: str) -> str:
    return f"{schema}.{name}" if schema else name


@dataclass
class EffectivePolicy:
    """The merged, most-restrictive policy for one (connection, role)."""

    max_rows: int | None = None
    max_runtime_seconds: int | None = None
    # None = no allow-restriction; otherwise the *intersection* of allow-lists.
    allowed_tables: set[str] | None = None
    blocked_tables: set[str] = field(default_factory=set)
    blocked_columns: set[str] = field(default_factory=set)
    masked_columns: set[str] = field(default_factory=set)
    row_filters: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def has_sql_rules(self) -> bool:
        return bool(
            self.allowed_tables is not None
            or self.blocked_tables
            or self.blocked_columns
            or self.row_filters
        )


def _applies(policy: DataPolicy, role: str | None) -> bool:
    if not policy.enabled:
        return False
    roles = policy.applies_to_roles or []
    return not roles or (role in roles)


def merge_policies(policies: list[DataPolicy], role: str | None) -> EffectivePolicy | None:
    """Merge applicable policies into one EffectivePolicy, or None if none apply."""
    applicable = [p for p in policies if _applies(p, role)]
    if not applicable:
        return None

    eff = EffectivePolicy()
    for p in sorted(applicable, key=lambda x: x.priority):
        if p.max_rows is not None:
            eff.max_rows = p.max_rows if eff.max_rows is None else min(eff.max_rows, p.max_rows)
        if p.max_runtime_seconds is not None:
            eff.max_runtime_seconds = (
                p.max_runtime_seconds
                if eff.max_runtime_seconds is None
                else min(eff.max_runtime_seconds, p.max_runtime_seconds)
            )
        if p.allowed_tables:
            allow = {_norm(x) for x in p.allowed_tables}
            eff.allowed_tables = allow if eff.allowed_tables is None else eff.allowed_tables & allow
        eff.blocked_tables |= {_norm(x) for x in (p.blocked_tables or [])}
        eff.blocked_columns |= {_norm(x) for x in (p.blocked_columns or [])}
        eff.masked_columns |= {_norm(x) for x in (p.masked_columns or [])}
        for k, v in (p.row_filters or {}).items():
            key = _norm(k)
            if key in eff.row_filters:
                eff.row_filters[key] = f"({eff.row_filters[key]}) AND ({v})"
            else:
                eff.row_filters[key] = v
        eff.sources.append(p.name)
    return eff


async def resolve_effective(
    db: AsyncSession, connection_id: uuid.UUID, role: str | None
) -> EffectivePolicy | None:
    """Load + merge the policies that apply to ``role`` on this connection."""
    result = await db.execute(
        select(DataPolicy).where(
            DataPolicy.connection_id == connection_id,
            DataPolicy.enabled.is_(True),
        )
    )
    return merge_policies(list(result.scalars().all()), role)


# --------------------------------------------------------------------------- #
# Enforcement
# --------------------------------------------------------------------------- #
def _table_matches(schema: str | None, name: str, entries: set[str]) -> bool:
    return name in entries or _fqtn(schema, name) in entries


def _column_matches(tbl: tuple[str | None, str] | None, col: str, entries: set[str]) -> bool:
    if col in entries:
        return True
    return tbl is not None and f"{tbl[1]}.{col}" in entries


def enforce_sql(eff: EffectivePolicy, sql: str, dialect: str | None) -> str:
    """Enforce SQL-level rules; return the (possibly row-filtered) SQL.

    Raises :class:`PolicyViolationError` on a block or when the SQL can't be analyzed
    while SQL-level rules are in force (fail closed).
    """
    if not eff.has_sql_rules():
        return sql

    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        raise PolicyViolationError(
            "A data policy requires SQL analysis (sqlglot), which is not installed."
        ) from None

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception:
        raise PolicyViolationError("Query could not be analyzed for policy enforcement.") from None
    if tree is None:
        raise PolicyViolationError("Query could not be analyzed for policy enforcement.")

    # Referenced tables + alias map.
    referenced: list[tuple[str | None, str]] = []
    alias_map: dict[str, tuple[str | None, str]] = {}
    for t in tree.find_all(exp.Table):
        name = _norm(t.name) if t.name else ""
        if not name:
            continue
        schema = _norm(t.db) if t.db else None
        referenced.append((schema, name))
        alias_map[name] = (schema, name)
        if t.alias:
            alias_map[_norm(t.alias)] = (schema, name)

    # allow-list: every referenced table must be allowed.
    if eff.allowed_tables is not None:
        for schema, name in referenced:
            if not _table_matches(schema, name, eff.allowed_tables):
                raise PolicyViolationError(
                    f"Table '{_fqtn(schema, name)}' is not in the allowed set for your role."
                )

    # block-list.
    for schema, name in referenced:
        if _table_matches(schema, name, eff.blocked_tables):
            raise PolicyViolationError(
                f"Access to table '{_fqtn(schema, name)}' is blocked by policy."
            )

    # blocked columns (explicit references only).
    if eff.blocked_columns:
        distinct = set(alias_map.values())
        single = next(iter(distinct)) if len(distinct) == 1 else None
        for col in tree.find_all(exp.Column):
            cname = _norm(col.name) if col.name else ""
            if not cname or cname == "*":
                continue
            qual = _norm(col.table) if col.table else ""
            tbl = alias_map.get(qual) if qual else single
            if _column_matches(tbl, cname, eff.blocked_columns):
                raise PolicyViolationError(f"Column '{cname}' is blocked by policy.")

    # row filters: replace each matching table with a filtered subquery.
    if eff.row_filters:
        for t in list(tree.find_all(exp.Table)):
            name = _norm(t.name) if t.name else ""
            schema = _norm(t.db) if t.db else None
            filt = eff.row_filters.get(_fqtn(schema, name)) or eff.row_filters.get(name)
            if not filt:
                continue
            alias = t.alias or t.name
            try:
                inner_table = t.copy()
                inner_table.set("alias", None)
                inner = exp.select("*").from_(inner_table).where(filt)
                subq = exp.Subquery(
                    this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias))
                )
                t.replace(subq)
            except Exception:
                raise PolicyViolationError(
                    f"Row-level filter for table '{name}' could not be applied."
                ) from None

    return tree.sql(dialect=dialect)


def effective_limits(
    eff: EffectivePolicy | None, conn_max_rows: int, conn_timeout: int
) -> tuple[int, int]:
    """Tighten the connection's row/timeout caps with the policy's (min wins)."""
    max_rows = conn_max_rows
    timeout = conn_timeout
    if eff is not None:
        if eff.max_rows is not None:
            max_rows = min(max_rows, eff.max_rows)
        if eff.max_runtime_seconds is not None:
            timeout = min(timeout, eff.max_runtime_seconds)
    return max_rows, timeout


def mask_result(
    eff: EffectivePolicy | None, columns: list[str], rows: list[list]
) -> tuple[list[list], list[str]]:
    """Redact masked columns in ``rows`` by output-column name (star-safe).

    Returns ``(rows, masked_names)``. ``rows`` is unchanged when nothing matches.
    """
    if eff is None or not eff.masked_columns:
        return rows, []
    bare = {entry.split(".")[-1] for entry in eff.masked_columns}
    idxs = [i for i, c in enumerate(columns) if _norm(c) in bare]
    if not idxs:
        return rows, []
    masked_rows = []
    for row in rows:
        new = list(row)
        for i in idxs:
            new[i] = MASK_TOKEN
        masked_rows.append(new)
    return masked_rows, [columns[i] for i in idxs]


# --------------------------------------------------------------------------- #
# CRUD (connection-scoped; authorization is via require_connection_* deps)
# --------------------------------------------------------------------------- #
async def list_policies(db: AsyncSession, connection_id: uuid.UUID) -> list[DataPolicy]:
    result = await db.execute(
        select(DataPolicy)
        .where(DataPolicy.connection_id == connection_id)
        .order_by(DataPolicy.priority, DataPolicy.created_at)
    )
    return list(result.scalars().all())


async def get_policy(
    db: AsyncSession, connection_id: uuid.UUID, policy_id: uuid.UUID
) -> DataPolicy:
    policy = await db.get(DataPolicy, policy_id)
    if policy is None or policy.connection_id != connection_id:
        raise NotFoundError("DataPolicy", str(policy_id))
    return policy


async def create_policy(
    db: AsyncSession, connection_id: uuid.UUID, ctx: AuthContext, **data: Any
) -> DataPolicy:
    ctx.require_role(ROLE_EDITOR)
    conn = await db.get(DatabaseConnection, connection_id)
    if conn is None:
        raise NotFoundError("DatabaseConnection", str(connection_id))
    policy = DataPolicy(
        organization_id=conn.organization_id, connection_id=connection_id, **data
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    await audit_service.record(
        db,
        organization_id=conn.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.POLICY_CREATED,
        payload={
            "policy_id": str(policy.id),
            "name": policy.name,
            "connection_id": str(connection_id),
        },
    )
    return policy


async def update_policy(
    db: AsyncSession,
    connection_id: uuid.UUID,
    policy_id: uuid.UUID,
    ctx: AuthContext,
    updates: dict[str, Any],
) -> DataPolicy:
    ctx.require_role(ROLE_EDITOR)
    policy = await get_policy(db, connection_id, policy_id)
    for key, value in updates.items():
        setattr(policy, key, value)
    await db.flush()
    await db.refresh(policy)
    await audit_service.record(
        db,
        organization_id=policy.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.POLICY_UPDATED,
        payload={"policy_id": str(policy.id), "name": policy.name},
    )
    return policy


async def delete_policy(
    db: AsyncSession, connection_id: uuid.UUID, policy_id: uuid.UUID, ctx: AuthContext
) -> None:
    ctx.require_role(ROLE_EDITOR)
    policy = await get_policy(db, connection_id, policy_id)
    name = policy.name
    org_id = policy.organization_id
    await db.delete(policy)
    await db.flush()
    await audit_service.record(
        db,
        organization_id=org_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.POLICY_DELETED,
        payload={"policy_id": str(policy_id), "name": name},
    )
