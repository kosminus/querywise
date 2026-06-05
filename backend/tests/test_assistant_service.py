"""Unit tests for assistant_service.handle_turn branching (no DB/LLM needed).

The service's collaborators (connection lookup, context builder, LLM router,
agent, SQL generator, column resolver) are monkeypatched, so we assert only the
orchestration: intent → action shape, the editor-only gate, and dictionary's
column resolution / downgrade.
"""

import uuid
from types import SimpleNamespace

import pytest

from app.db.models.membership import ROLE_EDITOR, ROLE_VIEWER
from app.llm.agents.assistant_router import AssistantDecision
from app.services import assistant_service


def _ctx(role: str):
    rank = {ROLE_VIEWER: 1, ROLE_EDITOR: 2, "admin": 3}
    return SimpleNamespace(
        role=role,
        has_role=lambda minimum, _r=role: rank[_r] >= rank[minimum],
    )


@pytest.fixture(autouse=True)
def _patch_collaborators(monkeypatch):
    async def fake_get_connection(db, connection_id, ctx, write=False):
        return SimpleNamespace(connector_type="postgresql")

    async def fake_build_context(db, connection_id, message, dialect):
        return SimpleNamespace(prompt_context="CTX")

    def fake_route(message):
        return (object(), SimpleNamespace(model="fake"))

    monkeypatch.setattr(assistant_service, "get_connection", fake_get_connection)
    monkeypatch.setattr(assistant_service, "build_context", fake_build_context)
    monkeypatch.setattr(assistant_service, "route", fake_route)


def _patch_decision(monkeypatch, decision: AssistantDecision):
    class _FakeAgent:
        def __init__(self, *_a, **_k):
            pass

        async def route(self, *_a, **_k):
            return decision

    monkeypatch.setattr(assistant_service, "AssistantAgent", _FakeAgent)


async def _run(role=ROLE_EDITOR, message="x"):
    return await assistant_service.handle_turn(
        db=None, connection_id=uuid.uuid4(), message=message, history=[], ctx=_ctx(role)
    )


# --- question ----------------------------------------------------------------


async def test_question_returns_sql_preview(monkeypatch):
    _patch_decision(monkeypatch, AssistantDecision(intent="question", message="Here:"))

    async def fake_sql_only(db, connection_id, message, ctx):
        return {"generated_sql": "SELECT 1", "explanation": "ones"}

    monkeypatch.setattr(assistant_service, "generate_sql_only", fake_sql_only)

    result = await _run()
    assert result["action"]["type"] == "sql_preview"
    assert result["action"]["payload"]["sql"] == "SELECT 1"


async def test_question_with_no_sql_returns_plain_message(monkeypatch):
    _patch_decision(monkeypatch, AssistantDecision(intent="question", message="Here:"))

    async def fake_sql_only(db, connection_id, message, ctx):
        return {"generated_sql": "", "explanation": ""}

    monkeypatch.setattr(assistant_service, "generate_sql_only", fake_sql_only)

    result = await _run()
    assert "action" not in result


# --- glossary / metric / knowledge (uniform draft branch) --------------------


async def test_glossary_editor_gets_draft(monkeypatch):
    draft = {"term": "NPL", "definition": "d", "sql_expression": "stage = 3",
             "related_tables": [], "related_columns": []}
    _patch_decision(monkeypatch, AssistantDecision("glossary", "Draft:", payload=draft))
    result = await _run()
    assert result["action"]["type"] == "glossary_draft"
    assert result["action"]["payload"]["term"] == "NPL"


async def test_metric_editor_gets_draft(monkeypatch):
    draft = {"metric_name": "ecl_ratio", "display_name": "ECL Ratio", "description": "",
             "sql_expression": "SUM(a)/SUM(b)", "aggregation_type": "RATIO",
             "related_tables": [], "dimensions": []}
    _patch_decision(monkeypatch, AssistantDecision("metric", "Draft:", payload=draft))
    result = await _run()
    assert result["action"]["type"] == "metric_draft"
    assert result["action"]["payload"]["metric_name"] == "ecl_ratio"


async def test_knowledge_editor_gets_draft(monkeypatch):
    draft = {"title": "IFRS 9", "content": "body", "source_url": ""}
    _patch_decision(monkeypatch, AssistantDecision("knowledge", "Draft:", payload=draft))
    result = await _run()
    assert result["action"]["type"] == "knowledge_draft"
    assert result["action"]["payload"]["title"] == "IFRS 9"


@pytest.mark.parametrize("intent", ["glossary", "metric", "knowledge"])
async def test_draft_viewer_is_downgraded(monkeypatch, intent):
    _patch_decision(monkeypatch, AssistantDecision(intent, "Draft:", payload={"any": "thing"}))
    result = await _run(role=ROLE_VIEWER)
    assert "action" not in result
    assert "editor" in result["message"].lower()


# --- dictionary (column resolution) ------------------------------------------


async def test_dictionary_resolves_column_and_drafts(monkeypatch):
    draft = {"table_name": "exposures", "column_name": "stage",
             "entries": [{"raw_value": "1", "display_value": "Performing", "description": ""}]}
    _patch_decision(monkeypatch, AssistantDecision("dictionary", "Draft:", payload=draft))
    col_id = uuid.uuid4()

    async def fake_resolve(db, connection_id, table_name, column_name):
        assert table_name == "exposures" and column_name == "stage"
        return col_id

    monkeypatch.setattr(assistant_service, "_resolve_column_id", fake_resolve)

    result = await _run()
    assert result["action"]["type"] == "dictionary_draft"
    assert result["action"]["payload"]["column_id"] == str(col_id)
    assert len(result["action"]["payload"]["entries"]) == 1


async def test_dictionary_unknown_column_downgrades(monkeypatch):
    draft = {"table_name": "nope", "column_name": "missing", "entries": [{"raw_value": "1",
             "display_value": "x", "description": ""}]}
    _patch_decision(monkeypatch, AssistantDecision("dictionary", "Draft:", payload=draft))

    async def fake_resolve(db, connection_id, table_name, column_name):
        return None

    monkeypatch.setattr(assistant_service, "_resolve_column_id", fake_resolve)

    result = await _run()
    assert "action" not in result
    assert "couldn't find" in result["message"].lower()


async def test_dictionary_viewer_downgraded_before_resolution(monkeypatch):
    _patch_decision(
        monkeypatch,
        AssistantDecision("dictionary", "Draft:", payload={"table_name": "t",
                          "column_name": "c", "entries": [{"raw_value": "1",
                          "display_value": "x"}]}),
    )

    async def boom(*_a, **_k):
        raise AssertionError("column resolution must not run for viewers")

    monkeypatch.setattr(assistant_service, "_resolve_column_id", boom)

    result = await _run(role=ROLE_VIEWER)
    assert "action" not in result


# --- chat --------------------------------------------------------------------


async def test_chat_returns_message_only(monkeypatch):
    _patch_decision(monkeypatch, AssistantDecision("chat", "Hello there"))
    result = await _run(role=ROLE_VIEWER)
    assert result == {"message": "Hello there"}
