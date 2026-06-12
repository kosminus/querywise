"""Metric candidates from recurring aggregate shapes in query logs."""

from collections import defaultdict

from app.semantic_compiler.sqlmeta import SqlAnalysis
from app.semantic_compiler.types import KIND_METRIC, Evidence, Finding

_MIN_CALLS = 5


def _bare(column: str) -> str:
    return column.split(".")[-1]


def infer_log_metrics(
    log_analyses: list[tuple[SqlAnalysis, int]],
    existing_metric_findings: list[Finding],
) -> list[Finding]:
    """Aggregate+GROUP BY shapes recurring across logged queries, weighted by calls.

    Skips expressions already proposed from views (views are stronger evidence).
    """
    already_proposed = {f.payload["sql_expression"].lower() for f in existing_metric_findings}

    # (function, column) -> accumulated calls / dimensions / tables / example sql
    shapes: dict[tuple[str, str | None], dict] = defaultdict(
        lambda: {"calls": 0, "dimensions": set(), "tables": set(), "sql": None}
    )
    for analysis, calls in log_analyses:
        if not analysis.aggregates:
            continue
        for agg in analysis.aggregates:
            if agg.function == "count" and agg.column is None and not analysis.group_by:
                continue  # bare COUNT(*) with no dims is noise
            shape = shapes[(agg.function, agg.column)]
            shape["calls"] += max(calls, 1)
            shape["dimensions"].update(_bare(g) for g in analysis.group_by if "(" not in g)
            shape["tables"].update(analysis.tables)
            shape["sql"] = shape["sql"] or agg.sql

    findings: list[Finding] = []
    for (function, column), shape in shapes.items():
        if shape["calls"] < _MIN_CALLS or shape["sql"] is None:
            continue
        if shape["sql"].lower() in already_proposed:
            continue
        confidence = 0.5
        if shape["calls"] >= 20:
            confidence += 0.1
        if shape["calls"] >= 100:
            confidence += 0.1
        name_base = _bare(column) if column else "rows"
        findings.append(
            Finding(
                kind=KIND_METRIC,
                title=f"Recurring aggregate: {shape['sql']}",
                payload={
                    "metric_name": f"{function}_{name_base}".lower(),
                    "display_name": f"{function} {name_base}".replace("_", " ").title(),
                    "description": None,
                    "sql_expression": shape["sql"],
                    "aggregation_type": function,
                    "related_tables": sorted(shape["tables"]),
                    "dimensions": sorted(shape["dimensions"]),
                    "filters": {},
                },
                evidence=[
                    Evidence(
                        "query_logs",
                        f"aggregate ran {shape['calls']} times across logged queries",
                    )
                ],
                confidence=confidence,
            )
        )
    return findings
