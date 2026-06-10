"""Deterministic inference modules of the semantic layer compiler.

Pure unit tests: hand-built TableProfiles + a fake prober, no DB, no LLM.
"""

from app.semantic_compiler.inference import (
    infer_dead_tables,
    infer_dictionaries,
    infer_fanout_warnings,
    infer_glossary_entities,
    infer_joins,
    infer_pii,
    infer_tenant_scope,
    infer_view_metrics,
)
from app.semantic_compiler.sqlmeta import JoinPair, SqlAnalysis
from app.semantic_compiler.types import (
    KIND_RELATIONSHIP,
    ColumnProfile,
    Finding,
    TableProfile,
    Thresholds,
    ViewDef,
)


class FakeProber:
    """Canned answers: overlap probes, lookup labels, sample values."""

    def __init__(self, overlap: float = 1.0, lookup_rows=None, samples=None):
        self.overlap = overlap
        self.lookup_rows = lookup_rows or []
        self.samples = samples or {}
        self.queries: list[str] = []

    async def query(self, sql: str, max_rows: int = 1000):
        self.queries.append(sql)
        if "overlap" in sql:
            return [{"overlap": self.overlap}]
        return self.lookup_rows

    async def sample_values(self, schema, table, column, limit=20):
        return self.samples.get((table, column), [])


def col(name, data_type="bigint", pk=False, unique=False, **kwargs):
    return ColumnProfile(
        name=name, data_type=data_type, is_primary_key=pk, is_unique=unique, **kwargs
    )


def make_tables() -> list[TableProfile]:
    customers = TableProfile(
        schema_name="public",
        table_name="customers",
        row_count_estimate=200,
        columns=[
            col("id", pk=True),
            col("tenant_id"),
            col("email", "text"),
            col("status", "integer", n_distinct=4.0),
        ],
    )
    orders = TableProfile(
        schema_name="public",
        table_name="orders",
        row_count_estimate=2000,
        columns=[
            col("id", pk=True),
            col("tenant_id"),
            col("customer_id"),
            col("status", "integer", n_distinct=4.0),
            col("total_amount", "numeric"),
        ],
    )
    order_statuses = TableProfile(
        schema_name="public",
        table_name="order_statuses",
        row_count_estimate=4,
        columns=[col("id", "integer", pk=True), col("code", "text"), col("label", "text")],
    )
    customers_bak = TableProfile(
        schema_name="public",
        table_name="customers_bak",
        row_count_estimate=0,
        columns=[col("id"), col("email", "text")],
    )
    return [customers, orders, order_statuses, customers_bak]


# --- joins ------------------------------------------------------------------


async def test_join_inference_naming_plus_overlap():
    tables = make_tables()
    findings = await infer_joins(tables, [], FakeProber(overlap=0.99), Thresholds())
    by_key = {
        (
            f.payload["source_table"],
            f.payload["source_column"],
            f.payload["target_table"],
        ): f
        for f in findings
    }
    edge = by_key[("orders", "customer_id", "customers")]
    assert edge.payload["target_column"] == "id"
    assert edge.payload["cardinality"] == "N:1"
    assert edge.confidence >= 0.75  # naming 0.45 + overlap 0.35
    sources = {e.source for e in edge.evidence}
    assert {"naming", "value_overlap"} <= sources


async def test_join_inference_lookup_table_pattern():
    tables = make_tables()
    findings = await infer_joins(tables, [], FakeProber(overlap=0.99), Thresholds())
    keys = {
        (f.payload["source_table"], f.payload["source_column"], f.payload["target_table"])
        for f in findings
    }
    assert ("orders", "status", "order_statuses") in keys


async def test_join_inference_failed_probe_kills_candidate():
    tables = make_tables()
    findings = await infer_joins(tables, [], FakeProber(overlap=0.1), Thresholds())
    assert findings == []


async def test_join_inference_log_co_occurrence_boost():
    tables = make_tables()
    analysis = SqlAnalysis(
        tables=["orders", "customers"],
        join_pairs=[JoinPair("orders", "customer_id", "customers", "id")],
    )
    findings = await infer_joins(
        tables, [(analysis, 50, "query log")], FakeProber(overlap=0.99), Thresholds()
    )
    edge = next(f for f in findings if f.payload["source_column"] == "customer_id")
    assert edge.confidence >= 0.9  # naming + overlap + logs
    assert any(e.source == "query_logs" for e in edge.evidence)


async def test_join_inference_skips_declared_fks():
    tables = make_tables()
    from app.semantic_compiler.types import DeclaredFK

    tables[1].declared_fks.append(DeclaredFK("customer_id", "public", "customers", "id"))
    findings = await infer_joins(tables, [], FakeProber(overlap=0.99), Thresholds())
    keys = {(f.payload["source_table"], f.payload["source_column"]) for f in findings}
    assert ("orders", "customer_id") not in keys


# --- dictionaries -----------------------------------------------------------


async def test_dictionary_from_check_constraint():
    tables = make_tables()
    tables[0].column("status").check_in_values = ["1", "2", "3", "4"]
    findings = await infer_dictionaries(tables, [], FakeProber())
    finding = next(
        f for f in findings if f.payload["table"] == "customers" and f.payload["column"] == "status"
    )
    assert [e["raw_value"] for e in finding.payload["entries"]] == ["1", "2", "3", "4"]
    assert finding.confidence >= 0.8


async def test_dictionary_from_lookup_table_labels():
    tables = make_tables()
    rel = Finding(
        kind=KIND_RELATIONSHIP,
        title="orders.status -> order_statuses.id",
        payload={
            "source_table": "orders",
            "source_column": "status",
            "target_table": "order_statuses",
            "target_column": "id",
        },
        confidence=0.8,
    )
    prober = FakeProber(
        lookup_rows=[
            {"raw": 1, "display": "Pending"},
            {"raw": 2, "display": "Paid"},
        ]
    )
    findings = await infer_dictionaries(tables, [rel], prober)
    finding = next(
        f for f in findings if f.payload["table"] == "orders" and f.payload["column"] == "status"
    )
    assert finding.payload["entries"][0]["display_value"] == "Pending"
    assert finding.confidence >= 0.8


async def test_dictionary_from_most_common_vals():
    tables = make_tables()
    tables[0].columns.append(
        col(
            "segment",
            "character varying",
            n_distinct=3.0,
            most_common_vals=["retail", "corporate", "sme"],
        )
    )
    findings = await infer_dictionaries(tables, [], FakeProber())
    finding = next(f for f in findings if f.payload["column"] == "segment")
    assert {e["raw_value"] for e in finding.payload["entries"]} == {"retail", "corporate", "sme"}


# --- view metrics -----------------------------------------------------------


def test_view_metrics_from_aggregates():
    view = ViewDef("public", "v_monthly_revenue", "unused")
    analysis = SqlAnalysis(
        tables=["orders"],
        aggregates=[],
        group_by=["orders.tenant_id"],
        where_sql="orders.status = 3",
    )
    from app.semantic_compiler.sqlmeta import AggregateItem

    analysis.aggregates = [
        AggregateItem(
            sql="SUM(orders.total_amount)",
            function="sum",
            column="orders.total_amount",
            alias="revenue",
        )
    ]
    findings = infer_view_metrics([(view, analysis)])
    assert len(findings) == 1
    payload = findings[0].payload
    assert payload["metric_name"] == "monthly_revenue_revenue"
    assert payload["sql_expression"] == "SUM(orders.total_amount)"
    assert payload["aggregation_type"] == "sum"
    assert payload["dimensions"] == ["tenant_id"]
    assert payload["filters"] == {"where": "orders.status = 3"}
    assert findings[0].confidence >= 0.75


# --- refusal boundaries -----------------------------------------------------


def test_dead_table_detection():
    findings = infer_dead_tables(make_tables(), {"orders", "customers"}, logs_available=True)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.payload["table"] == "customers_bak"
    assert finding.confidence >= 0.9  # suffix + zero rows + never queried


def test_tenant_scope_detection():
    analyses = [
        (SqlAnalysis(tables=["orders"], where_columns=["orders.tenant_id"]), 10),
        (SqlAnalysis(tables=["customers"], where_columns=["customers.tenant_id"]), 5),
        (SqlAnalysis(tables=["orders"], where_columns=["orders.status"]), 1),
    ]
    # entity tables = customers, orders, products (lookup + _bak excluded);
    # tenant_id on 2 of 3 — log confirmation pushes it over the threshold.
    tables = make_tables()
    tables.append(
        TableProfile(
            schema_name="public",
            table_name="products",
            row_count_estimate=40,
            columns=[col("id", pk=True), col("sku", "text"), col("unit_price", "numeric")],
        )
    )
    findings = infer_tenant_scope(tables, analyses)
    finding = next(f for f in findings if f.payload["column"] == "tenant_id")
    assert "orders" in finding.payload["row_filters"]
    assert finding.confidence >= 0.7  # presence + known name + log fraction


def test_tenant_scope_needs_log_confirmation():
    tables = make_tables()
    tables.append(
        TableProfile(
            schema_name="public",
            table_name="products",
            row_count_estimate=40,
            columns=[col("id", pk=True), col("sku", "text"), col("unit_price", "numeric")],
        )
    )
    findings = infer_tenant_scope(tables, [])  # no query logs
    finding = next(f for f in findings if f.payload["column"] == "tenant_id")
    assert finding.confidence < 0.5  # stays below the default emit threshold


async def test_pii_name_and_value_signals():
    tables = make_tables()
    prober = FakeProber(samples={("customers", "email"): ["a@b.com", "c@d.org", None]})
    findings = await infer_pii(tables, prober)
    email = next(
        f for f in findings if f.payload["column"] == "email" and f.payload["table"] == "customers"
    )
    assert email.payload["category"] == "email"
    assert email.confidence >= 0.85


def test_fanout_warning_from_n1_edge():
    tables = make_tables()
    rel = Finding(
        kind=KIND_RELATIONSHIP,
        title="orders.customer_id -> customers.id",
        payload={
            "source_table": "orders",
            "source_column": "customer_id",
            "target_table": "customers",
            "target_column": "id",
            "cardinality": "N:1",
        },
        confidence=0.9,
    )
    # parent customers has no measure columns → no warning; orders as parent does
    rel2 = Finding(
        kind=KIND_RELATIONSHIP,
        title="order_items.order_id -> orders.id",
        payload={
            "source_table": "order_items",
            "source_column": "order_id",
            "target_table": "orders",
            "target_column": "id",
            "cardinality": "N:1",
        },
        confidence=0.9,
    )
    findings = infer_fanout_warnings(tables, [rel, rel2])
    warning = next(f for f in findings if f.payload["parent_table"] == "orders")
    assert "total_amount" in warning.payload["risky_columns"]
    assert "double-count" in warning.payload["guidance"]


def test_glossary_hub_entities():
    tables = make_tables()
    rel = Finding(
        kind=KIND_RELATIONSHIP,
        title="orders.customer_id -> customers.id",
        payload={
            "source_table": "orders",
            "source_column": "customer_id",
            "target_table": "customers",
            "target_column": "id",
        },
        confidence=0.9,
    )
    findings = infer_glossary_entities(tables, [rel], dead_table_names={"customers_bak"})
    terms = {f.payload["term"] for f in findings}
    assert "Customer" in terms
    assert all("customers_bak" not in f.payload["related_tables"] for f in findings)
    customer = next(f for f in findings if f.payload["term"] == "Customer")
    assert "orders.customer_id" in customer.payload["related_columns"]
