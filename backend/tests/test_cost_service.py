"""Unit tests for cost_service pure helpers: compute_cost + table extraction.

Aggregations are DB-backed and exercised via integration; here we cover the
pricing math and the SQL table extraction (skips without sqlglot).
"""

import pytest

from app.config import settings
from app.services import cost_service as svc


def test_compute_cost_scanned_bytes():
    # 1 TiB scanned at the default $6.25/TiB.
    assert svc.compute_cost({"scanned_bytes": 1024**4}, 100) == 6.25


def test_compute_cost_prefers_billed_over_scanned():
    cost = svc.compute_cost({"scanned_bytes": 2 * 1024**4, "billed_bytes": 1024**4}, 0)
    assert cost == 6.25


def test_compute_cost_zero_without_stats_or_time_price():
    assert svc.compute_cost({}, 5000) == 0.0
    assert svc.compute_cost(None, None) == 0.0


def test_compute_cost_time_fallback(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_second_usd", 0.01)
    # 2000 ms -> 2 s * $0.01 = $0.02, only when no warehouse stats present.
    assert svc.compute_cost({}, 2000) == 0.02
    # Warehouse stats present -> time fallback is NOT added.
    assert svc.compute_cost({"scanned_bytes": 1024**4}, 2000) == 6.25


def test_compute_cost_slot_and_dbu(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_slot_ms_usd", 0.001)
    monkeypatch.setattr(settings, "cost_per_dbu_usd", 0.5)
    assert svc.compute_cost({"slot_ms": 1000}, 0) == 1.0
    assert svc.compute_cost({"dbu": 4}, 0) == 2.0


# --- table extraction (needs sqlglot) --------------------------------------
pytest.importorskip("sqlglot")


def test_referenced_tables_extracts_tables():
    sql = "SELECT id FROM public.orders o JOIN users u ON u.id = o.uid"
    tables = svc._referenced_tables(sql, "postgresql")
    assert "public.orders" in tables
    assert "users" in tables


def test_referenced_tables_empty_on_none():
    assert svc._referenced_tables(None, "postgresql") == []
