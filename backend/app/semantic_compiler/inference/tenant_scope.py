"""Tenant/scope-column detection -> draft row-filter data policy.

A column that appears on several entity tables AND is filtered in most logged
queries is a multi-tenancy (or org/account scoping) key. Real schemas don't
carry the tenant column on every table (lookup tables never do; child tables
scope through their parent), so presence alone is a weak signal — the query
logs are the confirming evidence. Without log confirmation the score stays
below the default threshold, so single-tenant DBs aren't spammed.

The draft policy is a template — an admin must substitute the real tenant
value before enabling it.
"""

import re

from app.semantic_compiler.sqlmeta import SqlAnalysis
from app.semantic_compiler.types import KIND_ROW_FILTER, Evidence, Finding, TableProfile

_KNOWN_SCOPE_NAMES = {
    "tenant_id",
    "org_id",
    "organization_id",
    "company_id",
    "account_id",
    "workspace_id",
    "client_id",
}
_MIN_TABLE_FRACTION = 0.3
_MIN_LOG_FRACTION = 0.5
_DEAD_SUFFIX_RE = re.compile(r"_(bak|backup|old|tmp|temp|archive|deprecated)\d*$", re.IGNORECASE)
_LOOKUP_COLUMNS = {"id", "code", "label", "name", "description"}


def _is_entity_table(table: TableProfile) -> bool:
    """Base tables minus backups and id/code/label lookup tables."""
    if table.table_type != "table":
        return False
    if _DEAD_SUFFIX_RE.search(table.table_name):
        return False
    names = {c.name.lower() for c in table.columns}
    if names <= _LOOKUP_COLUMNS and (table.row_count_estimate or 0) <= 100:
        return False
    return True


def infer_tenant_scope(
    tables: list[TableProfile],
    log_analyses: list[tuple[SqlAnalysis, int]],
) -> list[Finding]:
    entity_tables = [t for t in tables if _is_entity_table(t)]
    if len(entity_tables) < 3:
        return []

    # column name -> entity tables that carry it
    carriers: dict[str, list[str]] = {}
    for table in entity_tables:
        for col in table.columns:
            name = col.name.lower()
            if name.endswith("_id") and not col.is_primary_key:
                carriers.setdefault(name, []).append(table.table_name)

    findings: list[Finding] = []
    for column, carrying_tables in carriers.items():
        table_fraction = len(carrying_tables) / len(entity_tables)
        if table_fraction < _MIN_TABLE_FRACTION or len(carrying_tables) < 2:
            continue

        score = 0.35
        evidence = [
            Evidence(
                "heuristic",
                f"column {column} present on {len(carrying_tables)} of "
                f"{len(entity_tables)} entity tables ({table_fraction:.0%})",
            )
        ]
        if column in _KNOWN_SCOPE_NAMES:
            score += 0.1
            evidence.append(Evidence("naming", f"{column} is a conventional scoping column"))

        if log_analyses:
            # Call-weighted, and only over queries touching carrier tables:
            # a query against a reference table can't be expected to filter by
            # tenant, and one-off statements (e.g. the compiler's own probes)
            # shouldn't dilute a hot production query that ran 10k times.
            carrier_set = {t.lower() for t in carrying_tables}
            relevant_weight = 0
            filtered_weight = 0
            for analysis, calls in log_analyses:
                if not (set(analysis.tables) & carrier_set):
                    continue
                weight = max(calls, 1)
                relevant_weight += weight
                if any(ref.split(".")[-1] == column for ref in analysis.where_columns):
                    filtered_weight += weight
            log_fraction = filtered_weight / relevant_weight if relevant_weight else 0.0
            if log_fraction >= _MIN_LOG_FRACTION:
                score += 0.3
                evidence.append(
                    Evidence(
                        "query_logs",
                        f"filtered in {log_fraction:.0%} of logged query volume "
                        "against the tables that carry it",
                    )
                )

        findings.append(
            Finding(
                kind=KIND_ROW_FILTER,
                title=f"Scoping column detected: {column}",
                payload={
                    "column": column,
                    "tables": sorted(carrying_tables),
                    "row_filters": {
                        t: f"{t}.{column} = :tenant_id" for t in sorted(carrying_tables)
                    },
                },
                evidence=evidence,
                confidence=min(score, 0.95),
            )
        )
    return findings
