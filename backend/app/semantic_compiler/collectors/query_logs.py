"""Query-log collector: pg_stat_statements, the revealed-preference semantic layer.

Requires the extension to be installed in the target DB and the connecting role
to be allowed to read other sessions' statements (``pg_read_all_stats`` or
superuser); degrades to an empty list otherwise.
"""

import logging

from app.semantic_compiler.types import LoggedQuery, Prober

logger = logging.getLogger(__name__)

_LOGS_SQL = """
SELECT query, calls, total_exec_time
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND query NOT ILIKE '%pg_catalog%'
  AND query NOT ILIKE '%pg_stat_statements%'
  AND query NOT ILIKE '%information_schema%'
ORDER BY calls DESC
LIMIT 500
"""


async def collect_query_logs(prober: Prober) -> tuple[list[LoggedQuery], bool]:
    try:
        rows = await prober.query(_LOGS_SQL, max_rows=500)
    except Exception as exc:
        logger.debug("pg_stat_statements unavailable: %s", exc)
        return [], False
    queries = [
        LoggedQuery(
            sql=r["query"],
            calls=int(r["calls"] or 1),
            total_time_ms=float(r["total_exec_time"] or 0.0),
        )
        for r in rows
        if r.get("query")
    ]
    return queries, True
