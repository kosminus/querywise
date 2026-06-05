"""Assistant Service — orchestrates one conversational turn.

Stateless: the caller passes recent history each turn. The assistant *never*
writes — it only classifies intent and drafts. Writes (creating a glossary term,
metric, dictionary entry, or knowledge document) ride the existing REST endpoints,
so authorization + embedding stay on their established paths.

Returns a dict shaped as ``{message, action?}`` where ``action`` is a
discriminated union (``sql_preview`` | ``glossary_draft`` | ``metric_draft`` |
``dictionary_draft`` | ``knowledge_draft``).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext
from app.core.telemetry import start_span
from app.db.models.membership import ROLE_EDITOR
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.llm.agents.assistant_router import AssistantAgent
from app.llm.router import route
from app.semantic.context_builder import build_context
from app.services.connection_service import get_connection
from app.services.query_service import generate_sql_only

_NO_EDITOR = (
    "Adding to the semantic layer needs editor access on this workspace. "
    "I can still help you query the data."
)


async def handle_turn(
    db: AsyncSession,
    connection_id: uuid.UUID,
    message: str,
    history: list[dict],
    ctx: AuthContext,
) -> dict:
    """Classify the user's message and return ``{message, action?}``.

    - ``question``   → generate SQL (reuses ``generate_sql_only``) → ``sql_preview``
    - ``glossary`` / ``metric`` / ``dictionary`` / ``knowledge`` → draft action (editors only)
    - ``chat``       → plain message, no action
    """
    # Read-authz + dialect. Raises 404/403 if the caller can't read the connection.
    conn = await get_connection(db, connection_id, ctx)

    with start_span("assistant_build_context", **{"connection_id": str(connection_id)}):
        context = await build_context(db, connection_id, message, dialect=conn.connector_type)

    provider, llm_config = route(message)
    agent = AssistantAgent(provider, llm_config)
    with start_span("assistant_route", **{"llm.model": llm_config.model}):
        decision = await agent.route(message, context.prompt_context, history)

    if decision.intent == "question":
        sql = await generate_sql_only(db, connection_id, message, ctx)
        if not sql.get("generated_sql"):
            return {"message": "I couldn't generate a query for that. Try rephrasing?"}
        return _msg(
            decision.message or "Here's a query for that:",
            "sql_preview",
            {"sql": sql["generated_sql"], "explanation": sql.get("explanation", "")},
        )

    if decision.intent in {"glossary", "metric", "knowledge"}:
        if not ctx.has_role(ROLE_EDITOR):
            return {"message": _NO_EDITOR}
        action_type = f"{decision.intent}_draft"
        return _msg(_confirm(decision.message), action_type, decision.payload)

    if decision.intent == "dictionary":
        if not ctx.has_role(ROLE_EDITOR):
            return {"message": _NO_EDITOR}
        payload = decision.payload
        column_id = await _resolve_column_id(
            db, connection_id, payload["table_name"], payload["column_name"]
        )
        if column_id is None:
            return {
                "message": (
                    f"I couldn't find a column named '{payload['column_name']}' on table "
                    f"'{payload['table_name']}' in this connection. "
                    "Has the schema been introspected?"
                )
            }
        return _msg(
            _confirm(decision.message),
            "dictionary_draft",
            {**payload, "column_id": str(column_id)},
        )

    return {"message": decision.message or "How can I help with your data?"}


def _msg(message: str, action_type: str, payload: dict) -> dict:
    return {"message": message, "action": {"type": action_type, "payload": payload}}


def _confirm(message: str) -> str:
    return message or "Here's a draft — review and confirm:"


async def _resolve_column_id(
    db: AsyncSession,
    connection_id: uuid.UUID,
    table_name: str,
    column_name: str,
) -> uuid.UUID | None:
    """Find a cached column id by (connection, table_name, column_name), case-insensitive."""
    result = await db.execute(
        select(CachedColumn.id)
        .join(CachedTable, CachedColumn.table_id == CachedTable.id)
        .where(
            CachedTable.connection_id == connection_id,
            func.lower(CachedTable.table_name) == table_name.lower(),
            func.lower(CachedColumn.column_name) == column_name.lower(),
        )
    )
    return result.scalar_one_or_none()
