"""Statistics collector: enriches ColumnProfiles from Postgres catalogs.

Reads ``pg_stats`` (null_frac, n_distinct, most_common_vals), CHECK ``IN``-list
constraints, enum types, and single-column unique indexes. Every sub-query is
best-effort: on permission errors the profiles simply stay un-enriched and the
collector reports the source as unavailable.

NOTE: ``pg_stats`` is empty until the target DB has been ANALYZEd.
"""

import logging
import re

from app.semantic_compiler.types import Prober, TableProfile

logger = logging.getLogger(__name__)

_PG_STATS_SQL = """
SELECT schemaname, tablename, attname, null_frac, n_distinct,
       most_common_vals::text::text[] AS mcv,
       most_common_freqs::float[] AS mcf
FROM pg_stats
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
"""

_CHECK_SQL = """
SELECT n.nspname AS schema, c.relname AS table, pg_get_constraintdef(con.oid) AS def
FROM pg_constraint con
JOIN pg_class c ON con.conrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE con.contype = 'c' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
"""

_ENUM_SQL = """
SELECT n.nspname AS schema, c.relname AS table, a.attname AS column,
       e.enumlabel AS label, e.enumsortorder AS sort
FROM pg_attribute a
JOIN pg_class c ON a.attrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
JOIN pg_type t ON a.atttypid = t.oid
JOIN pg_enum e ON e.enumtypid = t.oid
WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, a.attname, e.enumsortorder
"""

_UNIQUE_SQL = """
SELECT n.nspname AS schema, c.relname AS table, a.attname AS column
FROM pg_index i
JOIN pg_class c ON c.oid = i.indrelid
JOIN pg_namespace n ON c.relnamespace = n.oid
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
WHERE i.indisunique AND i.indnkeyatts = 1
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
"""

# pg_get_constraintdef renders IN-lists as:
#   CHECK ((stage = ANY (ARRAY[1, 2, 3])))                               -- int
#   CHECK (((segment)::text = ANY ((ARRAY['retail'::charactervarying, ...])::text[])))
_CHECK_IN_RE = re.compile(
    r"\(?\"?(\w+)\"?\)?(?:::[\w\s]+)?\s*=\s*ANY\s*\(+\s*ARRAY\[(.*?)\]", re.IGNORECASE
)


def _clean_literal(raw: str) -> str:
    """'active'::text -> active ; 3 -> 3"""
    value = raw.strip()
    value = re.sub(r"::[\w\s\"]+$", "", value).strip()
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    return value


async def collect_pg_stats(prober: Prober, tables: list[TableProfile]) -> bool:
    """Enrich `tables` in place. Returns True if pg_stats was readable."""
    by_name: dict[tuple[str, str], TableProfile] = {
        (t.schema_name, t.table_name): t for t in tables
    }

    available = False
    try:
        rows = await prober.query(_PG_STATS_SQL, max_rows=50000)
        available = True
        for row in rows:
            table = by_name.get((row["schemaname"], row["tablename"]))
            col = table.column(row["attname"]) if table else None
            if col is None:
                continue
            col.null_frac = row["null_frac"]
            col.n_distinct = row["n_distinct"]
            col.most_common_vals = list(row["mcv"]) if row["mcv"] else None
            col.most_common_freqs = list(row["mcf"]) if row["mcf"] else None
    except Exception as exc:
        logger.debug("pg_stats unavailable: %s", exc)

    try:
        for row in await prober.query(_CHECK_SQL, max_rows=10000):
            table = by_name.get((row["schema"], row["table"]))
            if table is None:
                continue
            match = _CHECK_IN_RE.search(row["def"] or "")
            if not match:
                continue
            col = table.column(match.group(1))
            if col is not None:
                col.check_in_values = [_clean_literal(v) for v in match.group(2).split(",")]
    except Exception as exc:
        logger.debug("pg_constraint unavailable: %s", exc)

    try:
        for row in await prober.query(_ENUM_SQL, max_rows=10000):
            table = by_name.get((row["schema"], row["table"]))
            col = table.column(row["column"]) if table else None
            if col is not None:
                col.enum_values = (col.enum_values or []) + [row["label"]]
    except Exception as exc:
        logger.debug("pg_enum unavailable: %s", exc)

    try:
        for row in await prober.query(_UNIQUE_SQL, max_rows=10000):
            table = by_name.get((row["schema"], row["table"]))
            col = table.column(row["column"]) if table else None
            if col is not None:
                col.is_unique = True
    except Exception as exc:
        logger.debug("pg_index unavailable: %s", exc)

    return available
