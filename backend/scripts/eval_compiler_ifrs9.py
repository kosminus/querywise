#!/usr/bin/env python3
"""Evaluate the semantic layer compiler against the IFRS 9 sample DB.

Ground truth is the hand-written seed metadata (``seed_ifrs9_metadata.py``):
10 glossary terms, 8 metrics, 43 dictionary entries — plus the 5 declared FK
edges (the run uses ``ignore_declared_fks`` so join inference is actually
exercised against a schema where the answer key exists).

Usage (stack must be up, IFRS 9 connection introspected):
    python backend/scripts/eval_compiler_ifrs9.py [--base-url http://localhost:8000]
        [--llm] [--min-confidence 0.4] [--skip-analyze]

By default the LLM naming pass is OFF so the eval is deterministic.
"""

import argparse
import re
import sys
import time

import httpx
from seed_ifrs9_metadata import DICTIONARY_ENTRIES, GLOSSARY_TERMS, METRICS

API_PREFIX = "/api/v1"

# Declared FK edges in tests/fixtures/sample_seed.sql — the join-inference answer key.
EXPECTED_RELATIONSHIPS = {
    ("facilities", "counterparty_id", "counterparties", "id"),
    ("exposures", "facility_id", "facilities", "id"),
    ("ecl_provisions", "exposure_id", "exposures", "id"),
    ("collateral", "facility_id", "facilities", "id"),
    ("staging_history", "facility_id", "facilities", "id"),
}


def get_ifrs9_connection_id(client: httpx.Client, name: str) -> str:
    """The IFRS 9 connection by name (not just the first connection — other
    connections, e.g. the opsdb fixture, may exist)."""
    response = client.get(f"{API_PREFIX}/connections")
    response.raise_for_status()
    for conn in response.json():
        if conn["name"] == name:
            print(f"  Using connection: {conn['name']} ({conn['id']})")
            return conn["id"]
    print(f"ERROR: no connection named {name!r}. Is AUTO_SETUP_SAMPLE_DB enabled?")
    sys.exit(1)


def normalize_sql(sql: str) -> str:
    """Whitespace/case-insensitive normalization; sqlglot when available."""
    try:
        import sqlglot

        return sqlglot.parse_one(sql, dialect="postgres").sql(dialect="postgres").lower()
    except Exception:
        return re.sub(r"\s+", "", sql.lower())


def aggregate_signature(sql: str) -> tuple[str, str] | None:
    """(function, bare column) — fuzzy identity for metric matching."""
    match = re.search(r"(sum|count|avg|min|max)\s*\(\s*(?:\w+\.)?(\w+|\*)", sql.lower())
    return (match.group(1), match.group(2)) if match else None


def run_compiler(client: httpx.Client, connection_id: str, args) -> dict:
    response = client.post(
        f"{API_PREFIX}/connections/{connection_id}/compilation/runs",
        json={
            "llm_enabled": args.llm,
            "min_confidence": args.min_confidence,
            "ignore_declared_fks": True,
        },
    )
    response.raise_for_status()
    run = response.json()
    print(f"Run {run['id']} started; waiting...")

    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(2)
        run = client.get(
            f"{API_PREFIX}/connections/{connection_id}/compilation/runs/{run['id']}"
        ).json()
        if run["status"] in ("completed", "failed"):
            break
        progress = run.get("progress") or {}
        print(f"  ... {progress.get('stage', run['status'])}")
    if run["status"] != "completed":
        print(f"Run did not complete: {run['status']} — {run.get('error')}")
        sys.exit(1)
    print(f"Run completed. Stats: {run['stats']}")
    return run


def fetch_findings(client: httpx.Client, connection_id: str) -> list[dict]:
    response = client.get(
        f"{API_PREFIX}/connections/{connection_id}/compilation/findings",
        params={"status": "proposed"},
    )
    response.raise_for_status()
    return response.json()


def eval_relationships(findings: list[dict]) -> tuple[str, list[bool], list[float]]:
    rels = [f for f in findings if f["kind"] == "relationship"]
    proposed = {
        (
            f["payload"]["source_table"],
            f["payload"]["source_column"],
            f["payload"]["target_table"],
            f["payload"]["target_column"],
        ): f["confidence"]
        for f in rels
    }
    matched = EXPECTED_RELATIONSHIPS & set(proposed)
    recall = len(matched) / len(EXPECTED_RELATIONSHIPS)
    precision = len(matched) / len(proposed) if proposed else 0.0
    correctness = [key in EXPECTED_RELATIONSHIPS for key in proposed]
    confidences = list(proposed.values())
    missed = EXPECTED_RELATIONSHIPS - matched
    line = f"relationships  recall {recall:.0%} ({len(matched)}/5)  precision {precision:.0%}"
    if missed:
        line += f"\n    missed: {sorted(missed)}"
    return line, correctness, confidences


def eval_dictionary(findings: list[dict]) -> tuple[str, list[bool], list[float]]:
    truth: set[tuple[str, str, str]] = set()
    for (table, column), entries in DICTIONARY_ENTRIES.items():
        for entry in entries:
            truth.add((table, column, str(entry["raw_value"])))

    proposed: set[tuple[str, str, str]] = set()
    correctness: list[bool] = []
    confidences: list[float] = []
    for f in findings:
        if f["kind"] != "dictionary":
            continue
        payload = f["payload"]
        hit_any = False
        for entry in payload.get("entries", []):
            key = (payload["table"], payload["column"], str(entry["raw_value"]))
            proposed.add(key)
            hit_any = hit_any or key in truth
        correctness.append(hit_any)
        confidences.append(f["confidence"])

    matched = truth & proposed
    recall = len(matched) / len(truth) if truth else 0.0
    precision = len(matched) / len(proposed) if proposed else 0.0
    return (
        f"dictionary     recall {recall:.0%} ({len(matched)}/{len(truth)})  "
        f"precision {precision:.0%} ({len(proposed)} proposed values)",
        correctness,
        confidences,
    )


def eval_metrics(findings: list[dict]) -> str:
    truth_sigs = {aggregate_signature(m["sql_expression"]): m["metric_name"] for m in METRICS}
    truth_sigs.pop(None, None)
    proposed = [f for f in findings if f["kind"] == "metric"]
    proposed_sigs = {aggregate_signature(f["payload"]["sql_expression"]) for f in proposed} - {None}
    matched = set(truth_sigs) & proposed_sigs
    missed = [truth_sigs[s] for s in set(truth_sigs) - matched]
    return (
        f"metrics        fuzzy recall {len(matched)}/{len(truth_sigs)} "
        f"(by aggregate+column)  {len(proposed)} proposed\n"
        f"    missed: {sorted(missed)}"
    )


def eval_glossary(findings: list[dict]) -> str:
    proposed = [f for f in findings if f["kind"] == "glossary"]
    covered = 0
    for term in GLOSSARY_TERMS:
        gt_tables = set(term.get("related_tables") or [])
        if any(gt_tables & set(f["payload"].get("related_tables") or []) for f in proposed):
            covered += 1
    return (
        f"glossary       table-coverage {covered}/{len(GLOSSARY_TERMS)} "
        f"(soft metric — entity naming can't recover domain terms like 'EAD' "
        f"from schema alone)  {len(proposed)} proposed"
    )


def calibration(correctness: list[bool], confidences: list[float]) -> str:
    right = [c for ok, c in zip(correctness, confidences, strict=False) if ok]
    wrong = [c for ok, c in zip(correctness, confidences, strict=False) if not ok]
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")  # noqa: E731
    return (
        f"confidence calibration: correct findings avg {mean(right):.2f} "
        f"({len(right)}), incorrect avg {mean(wrong):.2f} ({len(wrong)})"
    )


def maybe_analyze(args) -> None:
    """pg_stats is empty without ANALYZE; run it directly against sample-db."""
    if args.skip_analyze:
        return
    try:
        import asyncio

        import asyncpg

        async def _go():
            conn = await asyncpg.connect(args.sample_dsn)
            try:
                await conn.execute("ANALYZE")
            finally:
                await conn.close()

        asyncio.run(_go())
        print("ANALYZE on sampledb done.")
    except Exception as exc:
        print(f"WARNING: could not ANALYZE sampledb ({exc}) — pg_stats may be empty.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--sample-dsn", default="postgresql://sample:sample_dev@localhost:5433/sampledb"
    )
    parser.add_argument("--llm", action="store_true", help="enable the LLM naming pass")
    parser.add_argument("--min-confidence", type=float, default=0.4)
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--connection-name", default="IFRS 9 Sample DB")
    args = parser.parse_args()

    maybe_analyze(args)

    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        connection_id = get_ifrs9_connection_id(client, args.connection_name)
        run_compiler(client, connection_id, args)
        findings = fetch_findings(client, connection_id)

    print(f"\n{len(findings)} proposed findings\n" + "=" * 60)
    rel_line, rel_ok, rel_conf = eval_relationships(findings)
    dict_line, dict_ok, dict_conf = eval_dictionary(findings)
    print(rel_line)
    print(dict_line)
    print(eval_metrics(findings))
    print(eval_glossary(findings))
    print(calibration(rel_ok + dict_ok, rel_conf + dict_conf))


if __name__ == "__main__":
    main()
