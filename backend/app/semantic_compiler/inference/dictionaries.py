"""Dictionary inference: enumerable column values with display labels.

Evidence, strongest first: enum types, CHECK IN-lists, lookup tables reached
through an inferred/declared join (labels probed from the lookup), and
``pg_stats.most_common_vals`` on low-cardinality columns.
"""

import logging

from app.semantic_compiler.types import (
    KIND_DICTIONARY,
    KIND_RELATIONSHIP,
    ColumnProfile,
    Evidence,
    Finding,
    Prober,
    TableProfile,
)

logger = logging.getLogger(__name__)

_TEXTY_TYPES = ("text", "character varying", "varchar", "character", "char")
_INTY_TYPES = ("integer", "bigint", "smallint", "int")
_MAX_CARDINALITY = 25
_MAX_VALUE_LEN = 30
_LOOKUP_MAX_ROWS = 100
_LABEL_COLUMN_NAMES = ("label", "name", "description", "title", "display_name")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _entry_list(values: list[str]) -> list[dict]:
    return [
        {"raw_value": str(v), "display_value": str(v), "description": None, "sort_order": i + 1}
        for i, v in enumerate(values)
    ]


def _effective_n_distinct(col: ColumnProfile, row_count: int | None) -> float | None:
    """pg_stats stores n_distinct as a NEGATIVE fraction of the row count when
    the planner thinks distinct values scale with table size."""
    if col.n_distinct is None:
        return None
    if col.n_distinct >= 0:
        return col.n_distinct
    return -col.n_distinct * (row_count or 0)


def _is_enumerable_text(col: ColumnProfile, row_count: int | None) -> bool:
    if not any(col.data_type.lower().startswith(t) for t in _TEXTY_TYPES):
        return False
    n_distinct = _effective_n_distinct(col, row_count)
    if n_distinct is None or not (2 <= n_distinct <= _MAX_CARDINALITY):
        return False
    if not col.most_common_vals:
        return False
    return all(len(str(v)) <= _MAX_VALUE_LEN for v in col.most_common_vals)


def _is_coded_int(col: ColumnProfile, row_count: int | None) -> bool:
    if not any(col.data_type.lower().startswith(t) for t in _INTY_TYPES):
        return False
    n_distinct = _effective_n_distinct(col, row_count)
    return n_distinct is not None and 2 <= n_distinct <= _MAX_CARDINALITY


async def _lookup_entries(
    prober: Prober, lookup: TableProfile, key_column: str
) -> list[dict] | None:
    """Probe a small id/code/label table for raw->display mappings."""
    label_col = next((c for c in lookup.columns if c.name.lower() in _LABEL_COLUMN_NAMES), None)
    code_col = next((c for c in lookup.columns if c.name.lower() == "code"), None)
    if label_col is None and code_col is None:
        return None
    display = label_col or code_col
    sql = (
        f"SELECT {_quote(key_column)} AS raw, {_quote(display.name)} AS display "
        f"FROM {_quote(lookup.schema_name)}.{_quote(lookup.table_name)} "
        f"ORDER BY {_quote(key_column)} LIMIT {_LOOKUP_MAX_ROWS}"
    )
    rows = await prober.query(sql, max_rows=_LOOKUP_MAX_ROWS)
    if not rows:
        return None
    return [
        {
            "raw_value": str(r["raw"]),
            "display_value": str(r["display"]),
            "description": None,
            "sort_order": i + 1,
        }
        for i, r in enumerate(rows)
    ]


async def infer_dictionaries(
    tables: list[TableProfile],
    relationship_findings: list[Finding],
    prober: Prober,
) -> list[Finding]:
    # (source_table, source_column) -> (target table name, confidence)
    lookup_edges: dict[tuple[str, str], tuple[str, float]] = {}
    for f in relationship_findings:
        if f.kind != KIND_RELATIONSHIP:
            continue
        key = (f.payload["source_table"], f.payload["source_column"])
        lookup_edges[key] = (f.payload["target_table"], f.confidence)
    for table in tables:
        for fk in table.declared_fks:
            lookup_edges[(table.table_name, fk.source_column)] = (fk.target_table, 1.0)

    by_name = {t.table_name.lower(): t for t in tables}
    findings: list[Finding] = []

    for table in tables:
        if table.table_type != "table":
            continue
        for col in table.columns:
            if col.is_primary_key or col.name.lower().endswith("_id"):
                continue

            entries: list[dict] | None = None
            evidence: Evidence | None = None
            confidence = 0.0

            if col.enum_values:
                entries = _entry_list(col.enum_values)
                evidence = Evidence("constraint", f"enum type with {len(entries)} labels")
                confidence = 0.9
            elif col.check_in_values:
                entries = _entry_list(col.check_in_values)
                evidence = Evidence("constraint", f"CHECK constraint allows {len(entries)} values")
                confidence = 0.85
            elif (
                _is_coded_int(col, table.row_count_estimate)
                and (table.table_name, col.name) in lookup_edges
            ):
                target_name, rel_conf = lookup_edges[(table.table_name, col.name)]
                lookup = by_name.get(target_name.lower())
                if lookup is not None and (lookup.row_count_estimate or 0) <= _LOOKUP_MAX_ROWS:
                    try:
                        entries = await _lookup_entries(prober, lookup, "id")
                    except Exception as exc:
                        logger.debug("lookup probe failed for %s: %s", target_name, exc)
                        entries = None
                    if entries:
                        evidence = Evidence(
                            "value_overlap",
                            f"labels resolved from lookup table {target_name}",
                        )
                        confidence = 0.85 if rel_conf >= 0.7 else 0.65
            elif _is_enumerable_text(col, table.row_count_estimate):
                entries = _entry_list(col.most_common_vals or [])
                evidence = Evidence(
                    "pg_stats",
                    f"n_distinct={_effective_n_distinct(col, table.row_count_estimate):.0f}, "
                    "values from most_common_vals",
                )
                confidence = 0.6

            if not entries or evidence is None:
                continue
            findings.append(
                Finding(
                    kind=KIND_DICTIONARY,
                    title=f"Value dictionary: {table.table_name}.{col.name}",
                    payload={
                        "schema": table.schema_name,
                        "table": table.table_name,
                        "column": col.name,
                        "entries": entries,
                    },
                    evidence=[evidence],
                    confidence=confidence,
                )
            )
    return findings
