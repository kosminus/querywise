"""Semantic certification + versioning service (Phase 3 — Milestone 1).

Single home for the trust lifecycle shared by metrics, glossary terms, sample
queries, and saved queries. Each entity carries ``status``
(draft|in_review|certified|deprecated) and an integer ``version``; every content
edit and status transition appends a :class:`SemanticVersion` snapshot so the
entity has a changelog with the reviewer and reason.

Role gate: ``in_review`` and revert-to-``draft`` require *editor*; ``certified``
and ``deprecated`` require *admin* (the trust gate). Certifying validates the
entity's SQL (read-only blocklist + a best-effort sqlglot parse).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext
from app.core.exceptions import AppError, ValidationError
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR
from app.db.models.semantic_version import (
    ENTITY_GLOSSARY,
    ENTITY_METRIC,
    ENTITY_SAMPLE_QUERY,
    ENTITY_SAVED_QUERY,
    ENTITY_TYPES,
    SemanticVersion,
)
from app.utils.sql_sanitizer import check_sql_safety

# Lifecycle states.
STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_CERTIFIED = "certified"
STATUS_DEPRECATED = "deprecated"
STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_CERTIFIED, STATUS_DEPRECATED)

# Allowed source -> target transitions. (draft -> certified is an admin fast-path.)
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_IN_REVIEW, STATUS_CERTIFIED},
    STATUS_IN_REVIEW: {STATUS_DRAFT, STATUS_CERTIFIED},
    STATUS_CERTIFIED: {STATUS_DRAFT, STATUS_DEPRECATED},
    STATUS_DEPRECATED: {STATUS_DRAFT},
}

# Minimum role required to move *to* a given status.
_ROLE_FOR_TARGET: dict[str, str] = {
    STATUS_DRAFT: ROLE_EDITOR,
    STATUS_IN_REVIEW: ROLE_EDITOR,
    STATUS_CERTIFIED: ROLE_ADMIN,
    STATUS_DEPRECATED: ROLE_ADMIN,
}

# Content fields captured in each entity's snapshot, per type.
_SNAPSHOT_FIELDS: dict[str, tuple[str, ...]] = {
    ENTITY_METRIC: (
        "metric_name",
        "display_name",
        "description",
        "sql_expression",
        "aggregation_type",
        "related_tables",
        "dimensions",
        "filters",
    ),
    ENTITY_GLOSSARY: (
        "term",
        "definition",
        "sql_expression",
        "related_tables",
        "related_columns",
        "examples",
    ),
    ENTITY_SAMPLE_QUERY: (
        "natural_language",
        "sql_query",
        "description",
        "tags",
        "is_validated",
    ),
    ENTITY_SAVED_QUERY: (
        "name",
        "description",
        "nl_question",
        "pinned_sql",
        "params",
        "is_public",
    ),
}

# The SQL-bearing field validated on certification, per type.
_SQL_FIELD: dict[str, str] = {
    ENTITY_METRIC: "sql_expression",
    ENTITY_GLOSSARY: "sql_expression",
    ENTITY_SAMPLE_QUERY: "sql_query",
    ENTITY_SAVED_QUERY: "pinned_sql",
}


def _require_known_type(entity_type: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise AppError(f"Unknown semantic entity type '{entity_type}'.", status_code=400)


def serialize(entity_type: str, entity: Any) -> dict[str, Any]:
    """Snapshot an entity's content fields into a JSON-friendly dict."""
    _require_known_type(entity_type)
    snap: dict[str, Any] = {}
    for field in _SNAPSHOT_FIELDS[entity_type]:
        value = getattr(entity, field, None)
        # ARRAY columns may come back as None; normalize for stable diffs.
        snap[field] = value
    return snap


async def snapshot(
    db: AsyncSession,
    ctx: AuthContext,
    entity_type: str,
    entity: Any,
    *,
    reason: str | None = None,
) -> SemanticVersion:
    """Append a :class:`SemanticVersion` row capturing the entity's current state."""
    _require_known_type(entity_type)
    row = SemanticVersion(
        organization_id=entity.organization_id,
        connection_id=entity.connection_id,
        entity_type=entity_type,
        entity_id=entity.id,
        version=entity.version,
        status=entity.status,
        snapshot=serialize(entity_type, entity),
        change_reason=reason,
        changed_by_id=ctx.user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def record_edit(
    db: AsyncSession,
    ctx: AuthContext,
    entity_type: str,
    entity: Any,
    *,
    reason: str | None = None,
) -> SemanticVersion:
    """Bump the entity's version and snapshot the new state (call after a content edit)."""
    entity.version = (entity.version or 1) + 1
    row = await snapshot(db, ctx, entity_type, entity, reason=reason or "edited")
    # The UPDATE expires the server-side ``onupdate`` timestamp; refresh so the
    # response serializer doesn't trigger a lazy load outside the async context.
    await db.refresh(entity)
    return row


def _validate_sql_for_certify(entity_type: str, entity: Any) -> None:
    """Lightweight pre-certification SQL check: read-only blocklist + parse."""
    sql = getattr(entity, _SQL_FIELD[entity_type], None)
    if not sql or not str(sql).strip():
        return
    issues = check_sql_safety(str(sql))
    if issues:
        raise ValidationError(
            "Cannot certify: SQL failed the read-only safety check — " + "; ".join(issues)
        )
    # Best-effort parse for full statements (fragments like glossary expressions
    # are skipped). A parse error blocks certification with a clear message.
    stripped = str(sql).lstrip().lower()
    if entity_type in (ENTITY_SAVED_QUERY, ENTITY_SAMPLE_QUERY) or stripped.startswith(
        ("select", "with")
    ):
        try:
            import sqlglot

            sqlglot.parse_one(str(sql))
        except ImportError:
            # sqlglot not installed — skip parse validation, keep the blocklist guard.
            pass
        except Exception as exc:  # sqlglot.errors.ParseError and friends
            raise ValidationError(f"Cannot certify: SQL did not parse — {exc}") from exc


async def transition_status(
    db: AsyncSession,
    ctx: AuthContext,
    entity_type: str,
    entity: Any,
    new_status: str,
    *,
    reason: str | None = None,
) -> Any:
    """Validate + apply a status transition, stamping certification and snapshotting."""
    _require_known_type(entity_type)
    current = entity.status or STATUS_DRAFT
    if new_status not in STATUSES:
        raise ValidationError(f"Unknown status '{new_status}'.")
    if new_status == current:
        raise ValidationError(f"Entity is already '{current}'.")
    if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValidationError(f"Cannot transition from '{current}' to '{new_status}'.")

    ctx.require_role(_ROLE_FOR_TARGET[new_status])

    if new_status == STATUS_CERTIFIED:
        _validate_sql_for_certify(entity_type, entity)
        entity.certified_by_id = ctx.user_id
        entity.certified_at = datetime.now(UTC)
    elif new_status == STATUS_DRAFT:
        # Re-opening clears the certification stamp.
        entity.certified_by_id = None
        entity.certified_at = None

    entity.status = new_status
    await snapshot(db, ctx, entity_type, entity, reason=reason or f"status → {new_status}")
    # Refresh server-side ``onupdate`` columns expired by the UPDATE (see record_edit).
    await db.refresh(entity)
    return entity


async def list_versions(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[SemanticVersion]:
    """Return the changelog for an entity, newest first."""
    _require_known_type(entity_type)
    result = await db.execute(
        select(SemanticVersion)
        .where(
            SemanticVersion.entity_type == entity_type,
            SemanticVersion.entity_id == entity_id,
        )
        .order_by(SemanticVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def get_version(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID, version: int
) -> SemanticVersion | None:
    """Return the most recent snapshot row at a given version number."""
    _require_known_type(entity_type)
    result = await db.execute(
        select(SemanticVersion)
        .where(
            SemanticVersion.entity_type == entity_type,
            SemanticVersion.entity_id == entity_id,
            SemanticVersion.version == version,
        )
        .order_by(SemanticVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Field-level diff between two snapshots: {field: {before, after}} for changed fields."""
    before = before or {}
    after = after or {}
    changed: dict[str, dict[str, Any]] = {}
    for key in set(before) | set(after):
        b, a = before.get(key), after.get(key)
        if b != a:
            changed[key] = {"before": b, "after": a}
    return changed
