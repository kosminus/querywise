"""Join-path inference — the compiler's core trick.

Operational DBs routinely drop FK constraints for write performance, so join
paths must be inferred. Three independent evidence sources combine into one
confidence score:

1. naming convention   — ``orders.customer_id`` -> ``customers.id``  (~0.45)
2. value-overlap probe — sampled LEFT JOIN, >=95% of source values
                         resolve in the target                        (+0.35)
3. log co-occurrence   — the join appears in actual logged queries    (+0.15)

A failed probe (<50% overlap) kills the candidate outright: a name match with
disjoint values is a coincidence, not a join path.
"""

import logging
from dataclasses import dataclass, field

from app.semantic_compiler.inference.naming import plural_candidates, singularize
from app.semantic_compiler.sqlmeta import SqlAnalysis
from app.semantic_compiler.types import (
    KIND_RELATIONSHIP,
    Evidence,
    Finding,
    Prober,
    TableProfile,
    Thresholds,
)

logger = logging.getLogger(__name__)

_OVERLAP_SQL = """
SELECT count(*) FILTER (WHERE t.{tc} IS NOT NULL)::float / NULLIF(count(*), 0) AS overlap
FROM (SELECT {sc} AS v FROM {ss}.{st} WHERE {sc} IS NOT NULL LIMIT {limit}) s
LEFT JOIN {ts}.{tt} t ON t.{tc} = s.v
"""


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@dataclass
class _Candidate:
    source: TableProfile
    source_column: str
    target: TableProfile
    target_column: str
    score: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    dropped: bool = False

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.source.table_name,
            self.source_column,
            self.target.table_name,
            self.target_column,
        )


def _naming_candidates(
    tables: list[TableProfile], by_name: dict[str, TableProfile]
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for table in tables:
        if table.table_type != "table":
            continue
        singular = singularize(table.table_name.lower())
        for col in table.columns:
            name = col.name.lower()
            if col.is_primary_key or name == "id":
                continue

            target_names: list[str] = []
            if name.endswith("_id") and len(name) > 3:
                target_names = plural_candidates(name[:-3])
            else:
                # lookup-table pattern: orders.status -> order_statuses / statuses
                target_names = [f"{singular}_{p}" for p in plural_candidates(name)]
                target_names += plural_candidates(name)

            for target_name in target_names:
                target = by_name.get(target_name)
                if target is None or target.table_name == table.table_name:
                    continue
                target_col = target.column("id") or next(
                    (c for c in target.columns if c.is_primary_key), None
                )
                if target_col is None:
                    continue
                candidates.append(
                    _Candidate(
                        source=table,
                        source_column=col.name,
                        target=target,
                        target_column=target_col.name,
                        score=0.45,
                        evidence=[
                            Evidence(
                                "naming",
                                f"{table.table_name}.{col.name} matches "
                                f"{target.table_name}.{target_col.name} by convention",
                            )
                        ],
                    )
                )
                break  # best naming match only
    return candidates


def _merge_log_evidence(
    candidates: list[_Candidate],
    analyses: list[tuple[SqlAnalysis, int, str]],
    by_name: dict[str, TableProfile],
) -> list[_Candidate]:
    """Add co-occurrence evidence to naming candidates; create log-only candidates."""
    pair_weight: dict[tuple, tuple[int, str]] = {}
    for analysis, calls, origin in analyses:
        for pair in analysis.join_pairs:
            count, _ = pair_weight.get(pair.key(), (0, origin))
            pair_weight[pair.key()] = (count + max(calls, 1), origin)

    by_key = {c.key: c for c in candidates}
    for pair_key, (weight, origin) in pair_weight.items():
        (t1, c1), (t2, c2) = pair_key
        matched = None
        for st, sc, tt, tc in (
            (t1, c1, t2, c2),
            (t2, c2, t1, c1),
        ):
            matched = by_key.get((st, sc, tt, tc))
            if matched:
                break
        if matched is not None:
            matched.score += 0.15
            matched.evidence.append(
                Evidence("query_logs", f"join observed in workload ({origin}, weight {weight})")
            )
            continue

        # Log-only candidate: pick the direction whose right side is a key column.
        left, right = by_name.get(t1), by_name.get(t2)
        if left is None or right is None:
            continue
        for src, sc, tgt, tc in ((left, c1, right, c2), (right, c2, left, c1)):
            tgt_col = tgt.column(tc)
            if tgt_col is not None and (tgt_col.is_primary_key or tgt_col.is_unique):
                cand = _Candidate(
                    source=src,
                    source_column=sc,
                    target=tgt,
                    target_column=tc,
                    score=0.35,
                    evidence=[
                        Evidence(
                            "query_logs",
                            f"join observed in workload ({origin}, weight {weight}) "
                            "with no naming-convention match",
                        )
                    ],
                )
                by_key[cand.key] = cand
                candidates.append(cand)
                break
    return candidates


async def _probe_overlap(prober: Prober, cand: _Candidate, sample_rows: int) -> float | None:
    sql = _OVERLAP_SQL.format(
        sc=_quote(cand.source_column),
        ss=_quote(cand.source.schema_name),
        st=_quote(cand.source.table_name),
        ts=_quote(cand.target.schema_name),
        tt=_quote(cand.target.table_name),
        tc=_quote(cand.target_column),
        limit=int(sample_rows),
    )
    rows = await prober.query(sql, max_rows=1)
    if not rows:
        return None
    value = rows[0].get("overlap")
    return float(value) if value is not None else None


def _cardinality(cand: _Candidate) -> str | None:
    target_col = cand.target.column(cand.target_column)
    source_col = cand.source.column(cand.source_column)
    target_unique = bool(target_col and (target_col.is_primary_key or target_col.is_unique))
    source_unique = bool(source_col and (source_col.is_primary_key or source_col.is_unique))
    if target_unique and source_unique:
        return "1:1"
    if target_unique:
        return "N:1"
    if source_unique:
        return "1:N"
    return None


async def infer_joins(
    tables: list[TableProfile],
    analyses: list[tuple[SqlAnalysis, int, str]],
    prober: Prober,
    thresholds: Thresholds,
    ignore_declared_fks: bool = False,
) -> list[Finding]:
    """`analyses` = (parsed SQL, call weight, origin label) from views + logs."""
    by_name = {t.table_name.lower(): t for t in tables}

    declared: set[tuple[str, str, str, str]] = set()
    if not ignore_declared_fks:
        for table in tables:
            for fk in table.declared_fks:
                declared.add(
                    (table.table_name, fk.source_column, fk.target_table, fk.target_column)
                )

    candidates = _naming_candidates(tables, by_name)
    candidates = _merge_log_evidence(candidates, analyses, by_name)
    candidates = [c for c in candidates if c.key not in declared]
    candidates.sort(key=lambda c: c.score, reverse=True)

    probes_left = thresholds.probe_budget
    for cand in candidates:
        if probes_left <= 0:
            break
        if cand.source.table_type != "table" or cand.target.table_type != "table":
            continue
        probes_left -= 1
        try:
            overlap = await _probe_overlap(prober, cand, thresholds.probe_sample_rows)
        except Exception as exc:
            logger.debug("overlap probe failed for %s: %s", cand.key, exc)
            continue
        if overlap is None:
            continue
        detail = (
            f"{overlap:.0%} of {thresholds.probe_sample_rows} sampled "
            f"{cand.source.table_name}.{cand.source_column} values resolve in "
            f"{cand.target.table_name}.{cand.target_column}"
        )
        if overlap >= 0.95:
            cand.score += 0.35
            cand.evidence.append(Evidence("value_overlap", detail))
        elif overlap >= 0.70:
            cand.score += 0.15
            cand.evidence.append(Evidence("value_overlap", detail))
        elif overlap < 0.50:
            cand.dropped = True
            cand.evidence.append(Evidence("value_overlap", detail + " — candidate rejected"))

    findings: list[Finding] = []
    for cand in candidates:
        if cand.dropped:
            continue
        cardinality = _cardinality(cand)
        findings.append(
            Finding(
                kind=KIND_RELATIONSHIP,
                title=(
                    f"{cand.source.table_name}.{cand.source_column} → "
                    f"{cand.target.table_name}.{cand.target_column}"
                ),
                payload={
                    "source_schema": cand.source.schema_name,
                    "source_table": cand.source.table_name,
                    "source_column": cand.source_column,
                    "target_schema": cand.target.schema_name,
                    "target_table": cand.target.table_name,
                    "target_column": cand.target_column,
                    "cardinality": cardinality,
                },
                evidence=cand.evidence,
                confidence=min(cand.score, 0.98),
            )
        )
    return findings
