"""Glossary entity candidates: hub tables of the (inferred + declared) join graph.

Deterministic evidence + fallback definitions; the LLM annotation pass writes
the human-quality names and descriptions.
"""

from collections import defaultdict

from app.semantic_compiler.inference.naming import singularize
from app.semantic_compiler.types import (
    KIND_GLOSSARY,
    KIND_RELATIONSHIP,
    Evidence,
    Finding,
    TableProfile,
)

_MAX_ENTITIES = 8
_LOOKUP_COLUMNS = {"id", "code", "label", "name", "description"}


def _is_lookup_table(table: TableProfile) -> bool:
    names = {c.name.lower() for c in table.columns}
    return names <= _LOOKUP_COLUMNS and (table.row_count_estimate or 0) <= 100


def infer_glossary_entities(
    tables: list[TableProfile],
    relationship_findings: list[Finding],
    dead_table_names: set[str],
) -> list[Finding]:
    # target table -> list of "source.column" references pointing at it
    inbound: dict[str, list[str]] = defaultdict(list)
    for f in relationship_findings:
        if f.kind != KIND_RELATIONSHIP:
            continue
        p = f.payload
        inbound[p["target_table"].lower()].append(f"{p['source_table']}.{p['source_column']}")
    for table in tables:
        for fk in table.declared_fks:
            inbound[fk.target_table.lower()].append(f"{table.table_name}.{fk.source_column}")

    candidates: list[tuple[float, TableProfile, list[str]]] = []
    for table in tables:
        if table.table_type != "table":
            continue
        if table.table_name.lower() in dead_table_names or _is_lookup_table(table):
            continue
        refs = sorted(set(inbound.get(table.table_name.lower(), [])))
        if not refs and (table.row_count_estimate or 0) < 1:
            continue
        score = 0.55 + 0.05 * min(len(refs), 4)
        candidates.append((score, table, refs))

    candidates.sort(key=lambda c: (c[0], c[1].row_count_estimate or 0), reverse=True)

    findings: list[Finding] = []
    for score, table, refs in candidates[:_MAX_ENTITIES]:
        term = singularize(table.table_name).replace("_", " ").title()
        referenced_by = f" Referenced by: {', '.join(refs)}." if refs else ""
        definition = (
            f"Core entity stored in {table.qualified_name} "
            f"(~{table.row_count_estimate or 0} rows).{referenced_by}"
        )
        if table.comment:
            definition = f"{table.comment} {definition}"
        evidence = [
            Evidence(
                "heuristic",
                f"hub table with {len(refs)} inbound join reference(s)"
                if refs
                else "populated base table",
            )
        ]
        findings.append(
            Finding(
                kind=KIND_GLOSSARY,
                title=f"Entity: {term}",
                payload={
                    "term": term,
                    "definition": definition,  # LLM annotation improves this
                    "sql_expression": table.table_name,
                    "related_tables": [table.table_name] + sorted({r.split(".")[0] for r in refs}),
                    "related_columns": refs,
                    "examples": [],
                },
                evidence=evidence,
                confidence=min(score, 0.8),
            )
        )
    return findings
