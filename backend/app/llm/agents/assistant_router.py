"""Agent: Assistant Router — classifies a chat message and extracts drafts.

One structured-JSON LLM call. Mirrors :class:`QueryComposerAgent`: build messages,
call ``provider.complete``, parse with ``repair_json`` and degrade gracefully to a
plain chat reply when the model returns non-JSON or an unusable draft.
"""

import json
from dataclasses import dataclass

from app.llm.base_provider import BaseLLMProvider, LLMConfig, LLMMessage
from app.llm.prompts.assistant_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.llm.utils import repair_json

# Intents that carry a structured draft payload.
DRAFT_INTENTS = {"glossary", "metric", "dictionary", "knowledge"}
VALID_INTENTS = {"question", "chat"} | DRAFT_INTENTS


@dataclass
class AssistantDecision:
    intent: str
    message: str
    payload: dict | None = None


class AssistantAgent:
    def __init__(self, provider: BaseLLMProvider, config: LLMConfig):
        self.provider = provider
        self.config = config

    async def route(
        self,
        message: str,
        context: str,
        history: list[dict] | None = None,
    ) -> AssistantDecision:
        """Classify ``message`` and extract a draft payload when applicable."""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            context=context,
            history=_format_history(history),
            message=message,
        )
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.provider.complete(messages, self.config)

        try:
            parsed = json.loads(repair_json(response.content))
        except (json.JSONDecodeError, TypeError):
            # Non-JSON response — treat the raw text as a plain chat reply.
            return AssistantDecision(intent="chat", message=response.content.strip())

        intent = parsed.get("intent")
        if intent not in VALID_INTENTS:
            intent = "chat"

        message_text = (parsed.get("message") or "").strip()
        payload = None

        if intent in DRAFT_INTENTS:
            payload = _NORMALIZERS[intent](parsed.get("payload"))
            if payload is None:
                # Model claimed a draft intent but gave no usable payload.
                intent = "chat"

        return AssistantDecision(intent=intent, message=message_text, payload=payload)


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return "(no prior messages)"
    lines = []
    for turn in history:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


def _str(value) -> str:
    return str(value).strip() if value is not None else ""


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_glossary(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    term, definition = _str(raw.get("term")), _str(raw.get("definition"))
    if not term or not definition:
        return None
    return {
        "term": term,
        "definition": definition,
        "sql_expression": _str(raw.get("sql_expression")),
        "related_tables": _as_list(raw.get("related_tables")),
        "related_columns": _as_list(raw.get("related_columns")),
    }


def _normalize_metric(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    display_name = _str(raw.get("display_name")) or _str(raw.get("metric_name"))
    sql_expression = _str(raw.get("sql_expression"))
    if not display_name or not sql_expression:
        return None
    metric_name = _str(raw.get("metric_name")) or _slug(display_name)
    return {
        "metric_name": metric_name,
        "display_name": display_name,
        "description": _str(raw.get("description")),
        "sql_expression": sql_expression,
        "aggregation_type": _str(raw.get("aggregation_type")),
        "related_tables": _as_list(raw.get("related_tables")),
        "dimensions": _as_list(raw.get("dimensions")),
    }


def _normalize_dictionary(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    table_name, column_name = _str(raw.get("table_name")), _str(raw.get("column_name"))
    if not table_name or not column_name:
        return None
    entries = []
    for item in raw.get("entries") or []:
        if not isinstance(item, dict):
            continue
        raw_value, display_value = _str(item.get("raw_value")), _str(item.get("display_value"))
        if not raw_value or not display_value:
            continue
        entries.append(
            {
                "raw_value": raw_value,
                "display_value": display_value,
                "description": _str(item.get("description")),
            }
        )
    if not entries:
        return None
    return {"table_name": table_name, "column_name": column_name, "entries": entries}


def _normalize_knowledge(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    title, content = _str(raw.get("title")), _str(raw.get("content"))
    if not title or not content:
        return None
    return {"title": title, "content": content, "source_url": _str(raw.get("source_url"))}


_NORMALIZERS = {
    "glossary": _normalize_glossary,
    "metric": _normalize_metric,
    "dictionary": _normalize_dictionary,
    "knowledge": _normalize_knowledge,
}


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in text.lower())
    return "_".join(part for part in cleaned.split("_") if part) or "metric"
