"""Unit tests for saved_query_service param rendering + cache hashing (no DB)."""

import uuid

import pytest

from app.core.exceptions import AppError
from app.services import saved_query_service as svc


def _defs(*items):
    return [dict(item) for item in items]


# --------------------------------------------------------------------------- #
# render_sql — type coercion + escaping
# --------------------------------------------------------------------------- #
def test_render_string_escapes_single_quotes():
    sql = svc.render_sql(
        "select * from t where name = {{n}}",
        _defs({"name": "n", "type": "string"}),
        {"n": "O'Brien"},
    )
    assert sql == "select * from t where name = 'O''Brien'"


def test_render_number_inlined_bare_and_integers_have_no_decimal():
    sql = svc.render_sql(
        "select {{a}}, {{b}}",
        _defs({"name": "a", "type": "number"}, {"name": "b", "type": "number"}),
        {"a": 5, "b": 2.5},
    )
    assert sql == "select 5, 2.5"


def test_render_boolean_and_date():
    sql = svc.render_sql(
        "select {{b}} where d > {{d}}",
        _defs({"name": "b", "type": "boolean"}, {"name": "d", "type": "date"}),
        {"b": True, "d": "2024-01-31"},
    )
    assert sql == "select TRUE where d > '2024-01-31'"


def test_render_uses_default_when_value_missing():
    sql = svc.render_sql(
        "select {{r}}",
        _defs({"name": "r", "type": "string", "default": "EU"}),
        {},
    )
    assert sql == "select 'EU'"


def test_render_no_params_passthrough():
    assert svc.render_sql("select 1", None, None) == "select 1"


def test_render_rejects_unknown_placeholder():
    with pytest.raises(AppError):
        svc.render_sql("select {{missing}}", [], {})


def test_render_rejects_missing_required_param():
    with pytest.raises(AppError):
        svc.render_sql("select {{x}}", _defs({"name": "x", "type": "number"}), {})


@pytest.mark.parametrize(
    "ptype,value",
    [("number", "notnum"), ("number", True), ("boolean", "maybe"), ("date", "31-01-2024")],
)
def test_render_rejects_bad_types(ptype, value):
    with pytest.raises(AppError):
        svc.render_sql("select {{x}}", _defs({"name": "x", "type": ptype}), {"x": value})


def test_render_number_rejects_infinity():
    with pytest.raises(AppError):
        svc.render_sql("select {{x}}", _defs({"name": "x", "type": "number"}), {"x": float("inf")})


# --------------------------------------------------------------------------- #
# compute_sql_hash — determinism + sensitivity
# --------------------------------------------------------------------------- #
def test_sql_hash_is_deterministic():
    cid = uuid.uuid4()
    h1 = svc.compute_sql_hash("select 1", {"a": 1}, cid)
    h2 = svc.compute_sql_hash("select 1", {"a": 1}, cid)
    assert h1 == h2 and len(h1) == 64


def test_sql_hash_param_order_independent():
    cid = uuid.uuid4()
    h1 = svc.compute_sql_hash("select 1", {"a": 1, "b": 2}, cid)
    h2 = svc.compute_sql_hash("select 1", {"b": 2, "a": 1}, cid)
    assert h1 == h2


def test_sql_hash_changes_with_sql_params_or_connection():
    cid = uuid.uuid4()
    base = svc.compute_sql_hash("select 1", {"a": 1}, cid)
    assert base != svc.compute_sql_hash("select 2", {"a": 1}, cid)
    assert base != svc.compute_sql_hash("select 1", {"a": 2}, cid)
    assert base != svc.compute_sql_hash("select 1", {"a": 1}, uuid.uuid4())
