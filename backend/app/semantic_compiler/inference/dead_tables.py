"""Dead-table detection: candidates for blocking / retrieval de-boosting."""

import re

from app.semantic_compiler.types import KIND_DEAD_TABLE, Evidence, Finding, TableProfile

_DEAD_SUFFIX_RE = re.compile(r"_(bak|backup|old|tmp|temp|archive|deprecated)\d*$", re.IGNORECASE)


def infer_dead_tables(
    tables: list[TableProfile],
    referenced_tables: set[str],
    logs_available: bool,
) -> list[Finding]:
    """`referenced_tables` = tables seen in logged queries or view definitions."""
    findings: list[Finding] = []
    for table in tables:
        if table.table_type != "table":
            continue
        score = 0.0
        evidence: list[Evidence] = []
        if _DEAD_SUFFIX_RE.search(table.table_name):
            score += 0.6
            evidence.append(Evidence("naming", "name suffix suggests a backup/old copy"))
        if (table.row_count_estimate or 0) <= 0:
            score += 0.35
            evidence.append(Evidence("pg_stats", "row count estimate is zero"))
        if logs_available and table.table_name.lower() not in referenced_tables:
            score += 0.2
            evidence.append(Evidence("query_logs", "never referenced in logged queries or views"))

        if score < 0.5 or not evidence:
            continue
        findings.append(
            Finding(
                kind=KIND_DEAD_TABLE,
                title=f"Likely dead table: {table.table_name}",
                payload={"schema": table.schema_name, "table": table.table_name},
                evidence=evidence,
                confidence=min(score, 0.95),
            )
        )
    return findings
