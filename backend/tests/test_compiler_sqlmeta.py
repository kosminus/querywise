"""sqlmeta: SQL analysis for the semantic layer compiler."""

import pytest

pytest.importorskip("sqlglot")

from app.semantic_compiler.sqlmeta import analyze  # noqa: E402

VIEW_SQL = """
SELECT
    o.tenant_id,
    date_trunc('month', o.order_date) AS month,
    SUM(o.total_amount) AS revenue,
    COUNT(*) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.deleted_at IS NULL AND o.status = 3
GROUP BY o.tenant_id, date_trunc('month', o.order_date)
"""


def test_analyze_extracts_aggregates_and_dimensions():
    analysis = analyze(VIEW_SQL, dialect="postgres")
    assert analysis is not None
    assert sorted(analysis.tables) == ["customers", "orders"]

    functions = {a.function for a in analysis.aggregates}
    assert functions == {"sum", "count"}
    sum_agg = next(a for a in analysis.aggregates if a.function == "sum")
    assert sum_agg.column == "orders.total_amount"
    assert sum_agg.alias == "revenue"

    assert "orders.tenant_id" in analysis.group_by


def test_analyze_extracts_join_pairs_resolving_aliases():
    analysis = analyze(VIEW_SQL, dialect="postgres")
    assert analysis is not None
    assert len(analysis.join_pairs) == 1
    pair = analysis.join_pairs[0]
    assert pair.key() == (("customers", "id"), ("orders", "customer_id"))


def test_analyze_where_columns_and_text():
    analysis = analyze(VIEW_SQL, dialect="postgres")
    assert analysis is not None
    assert "orders.deleted_at" in analysis.where_columns
    assert "orders.status" in analysis.where_columns
    assert analysis.where_sql is not None
    assert "deleted_at" in analysis.where_sql.lower()


def test_analyze_unqualified_columns_single_table():
    analysis = analyze("SELECT SUM(total_amount) FROM orders WHERE tenant_id = 1")
    assert analysis is not None
    assert analysis.aggregates[0].column == "orders.total_amount"
    assert analysis.where_columns == ["orders.tenant_id"]


def test_analyze_degrades_on_garbage():
    assert analyze("") is None
    assert analyze("THIS IS NOT ((( SQL") is None
