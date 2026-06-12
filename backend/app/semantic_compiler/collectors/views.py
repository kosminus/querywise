"""View-definition collector. Handwritten views are crystallized business logic."""

import logging

from app.semantic_compiler.types import Prober, ViewDef

logger = logging.getLogger(__name__)

_VIEWS_SQL = """
SELECT schemaname, viewname, definition
FROM pg_views
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
  AND viewname NOT LIKE 'pg\\_%'
"""


async def collect_view_definitions(prober: Prober) -> tuple[list[ViewDef], bool]:
    try:
        rows = await prober.query(_VIEWS_SQL, max_rows=2000)
    except Exception as exc:
        logger.debug("pg_views unavailable: %s", exc)
        return [], False
    return (
        [
            ViewDef(schema_name=r["schemaname"], view_name=r["viewname"], sql=r["definition"])
            for r in rows
            if r.get("definition")
        ],
        True,
    )
