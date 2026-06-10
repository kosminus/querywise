"""Metric extraction from view definitions.

A handwritten view is business logic someone already wrote and tested: its
aggregates are metric definitions, its GROUP BY columns are dimensions, and
its WHERE clause is the canonical filter.
"""

from app.semantic_compiler.sqlmeta import SqlAnalysis
from app.semantic_compiler.types import KIND_METRIC, Evidence, Finding, ViewDef


def _bare(column: str) -> str:
    return column.split(".")[-1]


def _metric_name(view_name: str, alias: str | None, function: str, column: str | None) -> str:
    if alias:
        base = alias
    elif column:
        base = f"{function}_{_bare(column)}"
    else:
        base = function
    prefix = view_name.removeprefix("v_").removeprefix("vw_")
    return f"{prefix}_{base}".lower()


def infer_view_metrics(
    view_analyses: list[tuple[ViewDef, SqlAnalysis]],
    used_views: set[str] | None = None,
) -> list[Finding]:
    """`used_views` = view names seen in query logs (small confidence boost)."""
    used_views = used_views or set()
    findings: list[Finding] = []
    seen_expressions: set[str] = set()

    for view, analysis in view_analyses:
        if not analysis.aggregates:
            continue
        base_tables = [t for t in analysis.tables if t != view.view_name.lower()]
        dimensions = sorted({_bare(g) for g in analysis.group_by if "(" not in g})
        for agg in analysis.aggregates:
            expression_key = agg.sql.lower()
            if expression_key in seen_expressions:
                continue
            seen_expressions.add(expression_key)

            confidence = 0.75
            evidence = [
                Evidence(
                    "view",
                    f"aggregate {agg.sql} defined in view {view.view_name}"
                    + (f" (grouped by {', '.join(dimensions)})" if dimensions else ""),
                )
            ]
            if view.view_name.lower() in used_views:
                confidence += 0.05
                evidence.append(Evidence("query_logs", f"view {view.view_name} is queried"))

            findings.append(
                Finding(
                    kind=KIND_METRIC,
                    title=f"Metric from {view.view_name}: {agg.sql}",
                    payload={
                        "metric_name": _metric_name(
                            view.view_name, agg.alias, agg.function, agg.column
                        ),
                        "display_name": (agg.alias or agg.function).replace("_", " ").title(),
                        "description": None,  # LLM annotation fills this
                        "sql_expression": agg.sql,
                        "aggregation_type": agg.function,
                        "related_tables": base_tables,
                        "dimensions": dimensions,
                        "filters": {"where": analysis.where_sql} if analysis.where_sql else {},
                        "source_view": view.view_name,
                    },
                    evidence=evidence,
                    confidence=confidence,
                )
            )
    return findings
