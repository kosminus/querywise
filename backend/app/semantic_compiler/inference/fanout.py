"""Fan-out trap detection.

For every parent 1:N child join, summing a parent measure across the join
double-counts — the single most common class of silently-wrong SQL answers.
Emits a warning per risky edge listing the parent's numeric measure columns.
"""

from app.semantic_compiler.types import (
    KIND_FANOUT,
    KIND_RELATIONSHIP,
    Evidence,
    Finding,
    TableProfile,
)

_MEASURE_TYPES = ("numeric", "decimal", "double", "real", "money", "integer", "bigint")
_KEY_HINTS = ("id", "_id", "code", "status", "method", "stage", "type", "year", "month")


def _measure_columns(table: TableProfile) -> list[str]:
    measures = []
    for col in table.columns:
        if col.is_primary_key:
            continue
        name = col.name.lower()
        if any(name == hint or name.endswith(hint) for hint in _KEY_HINTS):
            continue
        if any(col.data_type.lower().startswith(t) for t in _MEASURE_TYPES):
            measures.append(col.name)
    return measures


def infer_fanout_warnings(
    tables: list[TableProfile],
    relationship_findings: list[Finding],
) -> list[Finding]:
    by_name = {t.table_name.lower(): t for t in tables}

    # (child, child_col, parent, parent_col, confidence) for every N:1 edge
    edges: list[tuple[str, str, str, str, float]] = []
    for f in relationship_findings:
        if f.kind != KIND_RELATIONSHIP or f.payload.get("cardinality") != "N:1":
            continue
        p = f.payload
        edges.append(
            (
                p["source_table"],
                p["source_column"],
                p["target_table"],
                p["target_column"],
                f.confidence,
            )
        )
    for table in tables:
        for fk in table.declared_fks:
            target = by_name.get(fk.target_table.lower())
            target_col = target.column(fk.target_column) if target else None
            if target_col is not None and (target_col.is_primary_key or target_col.is_unique):
                edges.append(
                    (table.table_name, fk.source_column, fk.target_table, fk.target_column, 1.0)
                )

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for child, child_col, parent, parent_col, rel_conf in edges:
        if (child, parent) in seen:
            continue
        seen.add((child, parent))
        parent_table = by_name.get(parent.lower())
        if parent_table is None:
            continue
        measures = _measure_columns(parent_table)
        if not measures:
            continue
        example = f"{parent}.{measures[0]}"
        findings.append(
            Finding(
                kind=KIND_FANOUT,
                title=f"Fan-out risk: {parent} ⋈ {child}",
                payload={
                    "parent_table": parent,
                    "child_table": child,
                    "join": {"child_column": child_col, "parent_column": parent_col},
                    "risky_columns": measures,
                    "guidance": (
                        f"Joining {parent} to {child} repeats each {parent} row once per "
                        f"matching {child} row. Aggregating {parent} measures (e.g. "
                        f"SUM({example})) across this join double-counts; aggregate "
                        f"before joining or use DISTINCT on {parent} keys."
                    ),
                },
                evidence=[
                    Evidence(
                        "heuristic",
                        f"{child}.{child_col} → {parent}.{parent_col} is N:1, so the "
                        f"reverse join direction fans out {parent} rows",
                    )
                ],
                confidence=min(0.9, rel_conf),
            )
        )
    return findings
