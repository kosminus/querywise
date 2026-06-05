"""Unit tests for the Assistant router agent (no DB/LLM needed)."""

from types import SimpleNamespace

import pytest

from app.llm.agents.assistant_router import (
    AssistantAgent,
    _normalize_dictionary,
    _normalize_glossary,
    _normalize_metric,
    _slug,
)
from app.llm.base_provider import LLMConfig


class _FakeProvider:
    """Returns a canned completion regardless of input."""

    def __init__(self, content: str):
        self._content = content

    async def complete(self, messages, config):
        return SimpleNamespace(content=self._content)


def _agent(content: str) -> AssistantAgent:
    return AssistantAgent(_FakeProvider(content), LLMConfig(model="fake"))


async def test_question_intent():
    agent = _agent('{"intent": "question", "message": "Here you go:", "payload": null}')
    decision = await agent.route("what is total ECL by stage?", context="ctx")
    assert decision.intent == "question"
    assert decision.message == "Here you go:"
    assert decision.payload is None


async def test_glossary_intent_extracts_draft():
    agent = _agent(
        '{"intent": "glossary", "message": "Draft:", "payload": '
        '{"term": "NPL", "definition": "non-performing loans", '
        '"sql_expression": "stage = 3", "related_tables": ["exposures"], '
        '"related_columns": ["stage"]}}'
    )
    decision = await agent.route("add term NPL = stage 3", context="ctx")
    assert decision.intent == "glossary"
    assert decision.payload["term"] == "NPL"
    assert decision.payload["sql_expression"] == "stage = 3"
    assert decision.payload["related_tables"] == ["exposures"]


async def test_metric_intent_extracts_draft():
    agent = _agent(
        '{"intent": "metric", "message": "Draft:", "payload": '
        '{"display_name": "ECL Coverage Ratio", "sql_expression": "SUM(ecl)/SUM(exposure)", '
        '"aggregation_type": "RATIO", "related_tables": ["ecl_provisions"], "dimensions": ["stage"]}}'
    )
    decision = await agent.route("define ECL coverage ratio", context="ctx")
    assert decision.intent == "metric"
    assert decision.payload["display_name"] == "ECL Coverage Ratio"
    # metric_name is derived from display_name when omitted
    assert decision.payload["metric_name"] == "ecl_coverage_ratio"
    assert decision.payload["dimensions"] == ["stage"]


async def test_dictionary_intent_extracts_entries():
    agent = _agent(
        '{"intent": "dictionary", "message": "Draft:", "payload": '
        '{"table_name": "exposures", "column_name": "stage", "entries": ['
        '{"raw_value": "1", "display_value": "Performing"},'
        '{"raw_value": "3", "display_value": "Non-performing", "description": "default"}]}}'
    )
    decision = await agent.route("stage 1 = performing, 3 = non-performing", context="ctx")
    assert decision.intent == "dictionary"
    assert decision.payload["column_name"] == "stage"
    assert len(decision.payload["entries"]) == 2
    assert decision.payload["entries"][1]["display_value"] == "Non-performing"


async def test_knowledge_intent_extracts_draft():
    agent = _agent(
        '{"intent": "knowledge", "message": "Draft:", "payload": '
        '{"title": "IFRS 9 staging", "content": "Assets move through three stages..."}}'
    )
    decision = await agent.route("remember this about IFRS 9...", context="ctx")
    assert decision.intent == "knowledge"
    assert decision.payload["title"] == "IFRS 9 staging"
    assert decision.payload["source_url"] == ""


async def test_chat_intent():
    agent = _agent('{"intent": "chat", "message": "Hi! Ask me about your data.", "payload": null}')
    decision = await agent.route("hello", context="ctx")
    assert decision.intent == "chat"
    assert "Ask me" in decision.message


async def test_malformed_json_degrades_to_chat():
    agent = _agent("Sorry, I'm just going to talk normally here.")
    decision = await agent.route("hello", context="ctx")
    assert decision.intent == "chat"
    assert decision.message == "Sorry, I'm just going to talk normally here."


async def test_unknown_intent_falls_back_to_chat():
    agent = _agent('{"intent": "delete_everything", "message": "no", "payload": null}')
    decision = await agent.route("x", context="ctx")
    assert decision.intent == "chat"


@pytest.mark.parametrize(
    "intent,payload",
    [
        ("glossary", '{"definition": "x"}'),  # missing term
        ("metric", '{"display_name": "X"}'),  # missing sql_expression
        ("dictionary", '{"table_name": "t", "column_name": "c", "entries": []}'),  # no entries
        ("knowledge", '{"title": "t"}'),  # missing content
    ],
)
async def test_draft_intent_without_usable_payload_downgrades(intent, payload):
    agent = _agent(f'{{"intent": "{intent}", "message": "hm", "payload": {payload}}}')
    decision = await agent.route("x", context="ctx")
    assert decision.intent == "chat"
    assert decision.payload is None


@pytest.mark.parametrize(
    "raw,expected_tables",
    [
        ({"term": "t", "definition": "d", "related_tables": "exposures"}, ["exposures"]),
        ({"term": "t", "definition": "d", "related_tables": ["a", "", "b"]}, ["a", "b"]),
        ({"term": "t", "definition": "d"}, []),
    ],
)
def test_normalize_glossary_coerces_lists(raw, expected_tables):
    assert _normalize_glossary(raw)["related_tables"] == expected_tables


def test_normalize_glossary_requires_term_and_definition():
    assert _normalize_glossary({"term": "", "definition": "d"}) is None
    assert _normalize_glossary({"term": "t", "definition": ""}) is None
    assert _normalize_glossary("not a dict") is None


def test_normalize_metric_derives_name_and_requires_sql():
    assert _normalize_metric({"display_name": "My Ratio", "sql_expression": "a/b"})[
        "metric_name"
    ] == "my_ratio"
    assert _normalize_metric({"display_name": "X"}) is None  # no sql
    assert _normalize_metric({"sql_expression": "a"}) is None  # no name


def test_normalize_dictionary_drops_incomplete_entries():
    result = _normalize_dictionary(
        {
            "table_name": "t",
            "column_name": "c",
            "entries": [
                {"raw_value": "1", "display_value": "One"},
                {"raw_value": "2"},  # missing display_value — dropped
            ],
        }
    )
    assert len(result["entries"]) == 1


@pytest.mark.parametrize(
    "text,expected",
    [("ECL Coverage Ratio", "ecl_coverage_ratio"), ("  ", "metric"), ("A/B %", "a_b")],
)
def test_slug(text, expected):
    assert _slug(text) == expected
