"""Unit tests for policy_service: merge, enforcement, masking.

Pure functions only — DataPolicy is stubbed with SimpleNamespace (the merge
reads attributes, not the ORM). enforce_sql tests skip cleanly without sqlglot.
"""

from types import SimpleNamespace

import pytest

from app.services import policy_service as svc
from app.services.policy_service import PolicyViolationError


def _policy(**kw):
    base = dict(
        enabled=True,
        priority=100,
        applies_to_roles=[],
        max_rows=None,
        max_runtime_seconds=None,
        allowed_tables=[],
        blocked_tables=[],
        blocked_columns=[],
        masked_columns=[],
        row_filters={},
        name="p",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- merge ------------------------------------------------------------------
def test_merge_none_when_no_policies():
    assert svc.merge_policies([], "viewer") is None


def test_merge_skips_inapplicable_roles():
    p = _policy(applies_to_roles=["admin"], max_rows=10)
    assert svc.merge_policies([p], "viewer") is None
    eff = svc.merge_policies([p], "admin")
    assert eff is not None and eff.max_rows == 10


def test_merge_takes_minimum_limits():
    eff = svc.merge_policies(
        [_policy(max_rows=100, max_runtime_seconds=30), _policy(max_rows=50)], "viewer"
    )
    assert eff.max_rows == 50
    assert eff.max_runtime_seconds == 30


def test_merge_allowed_tables_intersection():
    eff = svc.merge_policies(
        [_policy(allowed_tables=["a", "b"]), _policy(allowed_tables=["b", "c"])], "viewer"
    )
    assert eff.allowed_tables == {"b"}


def test_merge_unions_blocked_and_masked():
    eff = svc.merge_policies(
        [_policy(blocked_columns=["ssn"], masked_columns=["email"]),
         _policy(blocked_columns=["dob"])],
        "viewer",
    )
    assert eff.blocked_columns == {"ssn", "dob"}
    assert eff.masked_columns == {"email"}


def test_merge_row_filters_anded():
    eff = svc.merge_policies(
        [_policy(row_filters={"orders": "region = 'EU'"}),
         _policy(row_filters={"orders": "amount > 0"})],
        "viewer",
    )
    assert "AND" in eff.row_filters["orders"]


# --- effective_limits -------------------------------------------------------
def test_effective_limits_tightens_only():
    eff = svc.merge_policies([_policy(max_rows=10)], "viewer")
    assert svc.effective_limits(eff, 1000, 30) == (10, 30)
    # Policy looser than connection → connection wins.
    eff2 = svc.merge_policies([_policy(max_rows=5000)], "viewer")
    assert svc.effective_limits(eff2, 1000, 30) == (1000, 30)


def test_effective_limits_none_policy():
    assert svc.effective_limits(None, 1000, 30) == (1000, 30)


# --- masking ----------------------------------------------------------------
def test_mask_result_redacts_by_output_name():
    eff = svc.merge_policies([_policy(masked_columns=["users.email"])], "viewer")
    cols = ["id", "email"]
    rows = [[1, "a@b.c"], [2, "d@e.f"]]
    masked, names = svc.mask_result(eff, cols, rows)
    assert names == ["email"]
    assert masked == [[1, svc.MASK_TOKEN], [2, svc.MASK_TOKEN]]
    # Original rows untouched (new list returned).
    assert rows[0][1] == "a@b.c"


def test_mask_result_noop_when_no_match():
    eff = svc.merge_policies([_policy(masked_columns=["ssn"])], "viewer")
    rows = [[1, "x"]]
    masked, names = svc.mask_result(eff, ["id", "name"], rows)
    assert names == [] and masked is rows


def test_mask_result_none_policy():
    rows = [[1]]
    assert svc.mask_result(None, ["id"], rows) == (rows, [])


# --- enforcement (needs sqlglot) -------------------------------------------
sqlglot = pytest.importorskip("sqlglot")


def test_enforce_no_rules_returns_sql_unchanged():
    eff = svc.merge_policies([_policy(max_rows=10)], "viewer")  # limits only
    assert svc.enforce_sql(eff, "SELECT 1", "postgres") == "SELECT 1"


def test_enforce_blocked_table():
    eff = svc.merge_policies([_policy(blocked_tables=["secrets"])], "viewer")
    with pytest.raises(PolicyViolationError, match="secrets"):
        svc.enforce_sql(eff, "SELECT * FROM secrets", "postgres")


def test_enforce_allowed_table_violation():
    eff = svc.merge_policies([_policy(allowed_tables=["orders"])], "viewer")
    with pytest.raises(PolicyViolationError, match="users"):
        svc.enforce_sql(eff, "SELECT * FROM users", "postgres")
    # Allowed table passes through.
    assert "orders" in svc.enforce_sql(eff, "SELECT id FROM orders", "postgres")


def test_enforce_blocked_column():
    eff = svc.merge_policies([_policy(blocked_columns=["ssn"])], "viewer")
    with pytest.raises(PolicyViolationError, match="ssn"):
        svc.enforce_sql(eff, "SELECT ssn FROM people", "postgres")


def test_enforce_injects_row_filter():
    eff = svc.merge_policies([_policy(row_filters={"orders": "region = 'EU'"})], "viewer")
    out = svc.enforce_sql(eff, "SELECT id FROM orders", "postgres").lower()
    assert "region" in out and "eu" in out


def test_enforce_fails_closed_when_sql_cannot_be_parsed(monkeypatch):
    # When SQL-level rules are in force but the query can't be analyzed, the
    # engine must block (fail closed), never pass the query through unfiltered.
    def _boom(*a, **k):
        raise ValueError("parse error")

    monkeypatch.setattr(sqlglot, "parse_one", _boom)
    eff = svc.merge_policies([_policy(blocked_tables=["x"])], "viewer")
    with pytest.raises(PolicyViolationError):
        svc.enforce_sql(eff, "SELECT * FROM whatever", "postgres")
