"""Unit tests for dashboard_service access rules + filter passthrough (no DB)."""

import uuid
from types import SimpleNamespace

import pytest

from app.core.auth import AuthContext
from app.core.exceptions import AuthorizationError, NotFoundError
from app.db.models.dashboard import Dashboard
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from app.services import dashboard_service as svc
from app.services import saved_query_service


def _ctx(role=ROLE_EDITOR, *, org=None, ws=None, user=None) -> AuthContext:
    return AuthContext(
        user=SimpleNamespace(id=user or uuid.uuid4()),
        organization_id=org or uuid.uuid4(),
        workspace_id=ws or uuid.uuid4(),
        role=role,
    )


def _dashboard(ctx: AuthContext, *, is_public=True, owner=None) -> Dashboard:
    return Dashboard(
        id=uuid.uuid4(),
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        owner_id=owner if owner is not None else ctx.user_id,
        name="d",
        is_public=is_public,
    )


# --------------------------------------------------------------------------- #
# _assert_access — scope + role
# --------------------------------------------------------------------------- #
def test_same_workspace_read_ok():
    ctx = _ctx(ROLE_VIEWER)
    svc._assert_access(_dashboard(ctx), ctx)  # no raise


def test_cross_workspace_is_404():
    ctx = _ctx()
    d = _dashboard(ctx)
    other = _ctx(org=ctx.organization_id)  # same org, different workspace
    with pytest.raises(NotFoundError):
        svc._assert_access(d, other)


def test_cross_org_is_404():
    ctx = _ctx()
    d = _dashboard(ctx)
    other = _ctx(ws=ctx.workspace_id)  # same workspace id value, different org
    with pytest.raises(NotFoundError):
        svc._assert_access(d, other)


def test_private_dashboard_hidden_from_non_owner_non_admin():
    owner = uuid.uuid4()
    ctx = _ctx(ROLE_VIEWER)
    d = _dashboard(ctx, is_public=False, owner=owner)
    with pytest.raises(AuthorizationError):
        svc._assert_access(d, ctx)


def test_private_dashboard_visible_to_admin():
    owner = uuid.uuid4()
    ctx = _ctx(ROLE_ADMIN)
    d = _dashboard(ctx, is_public=False, owner=owner)
    svc._assert_access(d, ctx)  # no raise


def test_write_requires_editor():
    ctx = _ctx(ROLE_VIEWER)
    d = _dashboard(ctx)
    with pytest.raises(AuthorizationError):
        svc._assert_access(d, ctx, write=True)


def test_write_ok_for_editor():
    ctx = _ctx(ROLE_EDITOR)
    svc._assert_access(_dashboard(ctx), ctx, write=True)  # no raise


# --------------------------------------------------------------------------- #
# Dashboard filters flow through render_sql: only referenced params are used,
# extras are ignored. (Tiles share this mechanism with saved-query runs.)
# --------------------------------------------------------------------------- #
def test_dashboard_filter_reaches_referenced_param():
    sql = saved_query_service.render_sql(
        "SELECT * FROM t WHERE stage >= {{min_stage}}",
        [{"name": "min_stage", "type": "number"}],
        {"min_stage": 2, "region": "EU"},  # 'region' is an extra dashboard filter
    )
    assert sql == "SELECT * FROM t WHERE stage >= 2"


def test_extra_dashboard_filters_are_ignored():
    # A tile whose SQL references no params ignores all dashboard filter values.
    sql = saved_query_service.render_sql(
        "SELECT 1",
        [],
        {"region": "EU", "min_stage": 5},
    )
    assert sql == "SELECT 1"
