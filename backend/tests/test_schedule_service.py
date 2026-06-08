"""Unit tests for schedule_service: cron math + threshold evaluation.

Pure functions only — no DB. Cron tests skip cleanly when croniter (the
[scheduling] extra) isn't installed, mirroring the lineage/sqlglot pattern.
"""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import ValidationError
from app.services import schedule_service as svc

croniter = pytest.importorskip("croniter")


# --- cron -------------------------------------------------------------------
def test_compute_next_run_advances_to_next_slot():
    base = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    nxt = svc.compute_next_run("0 9 * * *", after=base)  # daily 09:00
    assert nxt == datetime(2026, 6, 9, 9, 0, tzinfo=UTC)


def test_compute_next_run_naive_base_treated_as_utc():
    nxt = svc.compute_next_run("*/15 * * * *", after=datetime(2026, 6, 8, 10, 7))
    assert nxt == datetime(2026, 6, 8, 10, 15, tzinfo=UTC)


def test_validate_cron_rejects_garbage():
    with pytest.raises(ValidationError):
        svc.validate_cron("not a cron")


# --- threshold --------------------------------------------------------------
def test_threshold_none_returns_none():
    assert svc.evaluate_threshold(None, {"row_count": 5}) is None


def test_threshold_row_count_met():
    th = {"metric": "row_count", "op": ">", "value": 10}
    assert svc.evaluate_threshold(th, {"row_count": 15}) is True
    assert svc.evaluate_threshold(th, {"row_count": 5}) is False


def test_threshold_column_value_first_row():
    th = {"metric": "amount", "op": ">=", "value": 100}
    result = {"columns": ["id", "amount"], "rows": [[1, 250], [2, 50]]}
    assert svc.evaluate_threshold(th, result) is True


def test_threshold_missing_column_returns_none():
    th = {"metric": "ghost", "op": ">", "value": 1}
    assert svc.evaluate_threshold(th, {"columns": ["a"], "rows": [[1]]}) is None


def test_threshold_non_numeric_compare_returns_none():
    th = {"metric": "name", "op": ">", "value": 5}
    result = {"columns": ["name"], "rows": [["alice"]]}
    assert svc.evaluate_threshold(th, result) is None


def test_threshold_unknown_op_returns_none():
    th = {"metric": "row_count", "op": "≈", "value": 5}
    assert svc.evaluate_threshold(th, {"row_count": 5}) is None
