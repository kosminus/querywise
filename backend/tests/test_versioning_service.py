"""Unit tests for versioning_service: transitions, role gating, cert stamping (no DB)."""

import uuid
from types import SimpleNamespace

import pytest

from app.core.auth import AuthContext
from app.core.exceptions import AuthorizationError, ValidationError
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from app.db.models.semantic_version import ENTITY_GLOSSARY, ENTITY_METRIC
from app.services import versioning_service as svc


class FakeSession:
    """Minimal stand-in for AsyncSession used by snapshot()."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj, attrs=None) -> None:
        pass


def _ctx(role=ROLE_EDITOR) -> AuthContext:
    return AuthContext(
        user=SimpleNamespace(id=uuid.uuid4()),
        organization_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        role=role,
    )


def _metric(status="draft", version=1, sql="SELECT sum(amount) FROM exposures") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        status=status,
        version=version,
        certified_by_id=None,
        certified_at=None,
        metric_name="ecl",
        display_name="ECL",
        description="expected credit loss",
        sql_expression=sql,
        aggregation_type="sum",
        related_tables=["exposures"],
        dimensions=[],
        filters={},
    )


# --------------------------------------------------------------------------- #
# Transition validity
# --------------------------------------------------------------------------- #
async def test_draft_to_in_review_ok_for_editor():
    db, ctx, m = FakeSession(), _ctx(ROLE_EDITOR), _metric()
    await svc.transition_status(db, ctx, ENTITY_METRIC, m, "in_review")
    assert m.status == "in_review"
    assert len(db.added) == 1  # one snapshot row


async def test_same_status_rejected():
    db, ctx, m = FakeSession(), _ctx(), _metric(status="draft")
    with pytest.raises(ValidationError):
        await svc.transition_status(db, ctx, ENTITY_METRIC, m, "draft")


async def test_illegal_transition_rejected():
    db, ctx, m = FakeSession(), _ctx(ROLE_ADMIN), _metric(status="draft")
    with pytest.raises(ValidationError):
        await svc.transition_status(db, ctx, ENTITY_METRIC, m, "deprecated")


# --------------------------------------------------------------------------- #
# Role gating
# --------------------------------------------------------------------------- #
async def test_certify_requires_admin():
    db, ctx, m = FakeSession(), _ctx(ROLE_EDITOR), _metric(status="in_review")
    with pytest.raises(AuthorizationError):
        await svc.transition_status(db, ctx, ENTITY_METRIC, m, "certified")


async def test_in_review_requires_editor():
    db, ctx, m = FakeSession(), _ctx(ROLE_VIEWER), _metric(status="draft")
    with pytest.raises(AuthorizationError):
        await svc.transition_status(db, ctx, ENTITY_METRIC, m, "in_review")


# --------------------------------------------------------------------------- #
# Certification stamping
# --------------------------------------------------------------------------- #
async def test_certify_stamps_owner_and_time():
    db, ctx, m = FakeSession(), _ctx(ROLE_ADMIN), _metric(status="in_review")
    await svc.transition_status(db, ctx, ENTITY_METRIC, m, "certified")
    assert m.status == "certified"
    assert m.certified_by_id == ctx.user_id
    assert m.certified_at is not None


async def test_revert_to_draft_clears_certification():
    db, ctx, m = FakeSession(), _ctx(ROLE_ADMIN), _metric(status="certified")
    m.certified_by_id = uuid.uuid4()
    m.certified_at = object()
    await svc.transition_status(db, ctx, ENTITY_METRIC, m, "draft")
    assert m.status == "draft"
    assert m.certified_by_id is None
    assert m.certified_at is None


async def test_certify_blocks_unsafe_sql():
    db, ctx = FakeSession(), _ctx(ROLE_ADMIN)
    m = _metric(status="in_review", sql="SELECT 1; DROP TABLE exposures")
    with pytest.raises(ValidationError):
        await svc.transition_status(db, ctx, ENTITY_METRIC, m, "certified")


# --------------------------------------------------------------------------- #
# Snapshots, edits, diff
# --------------------------------------------------------------------------- #
async def test_record_edit_bumps_version_and_snapshots():
    db, ctx, m = FakeSession(), _ctx(), _metric(version=3)
    await svc.record_edit(db, ctx, ENTITY_METRIC, m)
    assert m.version == 4
    assert db.added[0].version == 4
    assert db.added[0].snapshot["metric_name"] == "ecl"


def test_serialize_only_content_fields():
    snap = svc.serialize(
        ENTITY_GLOSSARY, _metric()
    )  # reuse namespace; glossary fields read via getattr
    assert set(snap) == {
        "term",
        "definition",
        "sql_expression",
        "related_tables",
        "related_columns",
        "examples",
    }


def test_diff_reports_changed_fields():
    d = svc.diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
    assert d == {"b": {"before": 2, "after": 3}, "c": {"before": None, "after": 4}}
