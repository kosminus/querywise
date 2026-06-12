"""Compiler engine: deterministic inference over collected evidence.

The service layer builds a ``CompilerInput`` via the collectors, then calls
``run_compiler``. The LLM annotation pass happens *after* this returns — the
engine itself never calls a model.
"""

import logging

from app.semantic_compiler.inference import (
    infer_dead_tables,
    infer_dictionaries,
    infer_fanout_warnings,
    infer_glossary_entities,
    infer_joins,
    infer_log_metrics,
    infer_pii,
    infer_tenant_scope,
    infer_view_metrics,
)
from app.semantic_compiler.sqlmeta import SqlAnalysis, analyze
from app.semantic_compiler.types import (
    CompilerInput,
    Finding,
    Prober,
    Thresholds,
    ViewDef,
)

logger = logging.getLogger(__name__)


def _apply_thresholds(findings: list[Finding], thresholds: Thresholds) -> list[Finding]:
    kept: list[Finding] = []
    by_kind: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.confidence >= thresholds.min_confidence:
            by_kind.setdefault(finding.kind, []).append(finding)
    for kind, group in by_kind.items():
        group.sort(key=lambda f: f.confidence, reverse=True)
        cap = thresholds.max_per_kind.get(kind)
        kept.extend(group[:cap] if cap else group)
    return kept


async def run_compiler(
    inp: CompilerInput, prober: Prober, thresholds: Thresholds | None = None
) -> list[Finding]:
    thresholds = thresholds or Thresholds()
    ignore_declared_fks = bool(inp.options.get("ignore_declared_fks"))

    # Parse views and logged queries once; weight = call count for logs.
    view_analyses: list[tuple[ViewDef, SqlAnalysis]] = []
    for view in inp.views:
        analysis = analyze(view.sql, dialect=inp.dialect)
        if analysis is not None:
            view_analyses.append((view, analysis))

    log_analyses: list[tuple[SqlAnalysis, int]] = []
    for logged in inp.logged_queries:
        analysis = analyze(logged.sql, dialect=inp.dialect)
        if analysis is not None:
            log_analyses.append((analysis, logged.calls))

    # Combined join evidence: views count once, logs by call weight.
    combined = [(a, 1, f"view {v.view_name}") for v, a in view_analyses] + [
        (a, calls, "query log") for a, calls in log_analyses
    ]

    relationships = await infer_joins(
        inp.tables, combined, prober, thresholds, ignore_declared_fks=ignore_declared_fks
    )

    dictionaries = await infer_dictionaries(inp.tables, relationships, prober)

    view_names_used = {
        t for a, _ in log_analyses for t in a.tables
    }  # views queried in the workload
    metrics = infer_view_metrics(view_analyses, used_views=view_names_used)
    metrics += infer_log_metrics(log_analyses, metrics)

    logs_available = inp.sources_available.get("query_logs", False)
    referenced: set[str] = set()
    for analysis, _ in log_analyses:
        referenced.update(analysis.tables)
    for _, analysis in view_analyses:
        referenced.update(analysis.tables)
    dead = infer_dead_tables(inp.tables, referenced, logs_available)
    dead_names = {f.payload["table"].lower() for f in dead}

    tenant = infer_tenant_scope(inp.tables, log_analyses)
    pii = await infer_pii(inp.tables, prober)
    fanout = infer_fanout_warnings(inp.tables, relationships)
    glossary = infer_glossary_entities(inp.tables, relationships, dead_names)

    all_findings = relationships + dictionaries + metrics + dead + tenant + pii + fanout + glossary
    kept = _apply_thresholds(all_findings, thresholds)
    logger.info("compiler produced %d findings (%d above threshold)", len(all_findings), len(kept))
    return kept


__all__ = ["run_compiler"]
