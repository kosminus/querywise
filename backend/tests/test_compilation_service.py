"""Annotator agent + service-level annotation merge (no DB, no LLM)."""

from types import SimpleNamespace

from app.llm.agents.semantic_annotator import SemanticAnnotatorAgent
from app.llm.base_provider import LLMConfig
from app.semantic_compiler.types import Evidence, Finding
from app.services import compilation_service


class _FakeProvider:
    def __init__(self, content: str):
        self._content = content
        self.calls = 0

    async def complete(self, messages, config):
        self.calls += 1
        return SimpleNamespace(content=self._content)


class _ExplodingProvider:
    async def complete(self, messages, config):
        raise RuntimeError("provider down")


def _agent(content: str) -> SemanticAnnotatorAgent:
    return SemanticAnnotatorAgent(_FakeProvider(content), LLMConfig(model="fake"))


_FINDINGS = [
    {"title": "Metric from v_monthly_revenue", "payload": {"metric_name": "x"}, "evidence": []},
    {"title": "Recurring aggregate", "payload": {"metric_name": "y"}, "evidence": []},
]


async def test_annotate_merges_allowed_fields():
    agent = _agent(
        '{"annotations": [{"index": 0, "metric_name": "Monthly Revenue!", '
        '"display_name": "Monthly Revenue", "description": "Total completed-order revenue."}]}'
    )
    result = await agent.annotate("metric", _FINDINGS)
    assert result[0]["metric_name"] == "monthly_revenue"  # sanitized to identifier
    assert result[0]["display_name"] == "Monthly Revenue"


async def test_annotate_rejects_unknown_indices_and_fields():
    agent = _agent(
        '{"annotations": ['
        '{"index": 7, "description": "phantom finding"},'
        '{"index": 1, "sql_expression": "SUM(invented)", "description": "ok"}]}'
    )
    result = await agent.annotate("metric", _FINDINGS)
    assert 7 not in result
    assert "sql_expression" not in result[1]  # structural field dropped
    assert result[1]["description"] == "ok"


async def test_annotate_swallows_provider_failure():
    agent = SemanticAnnotatorAgent(_ExplodingProvider(), LLMConfig(model="fake"))
    assert await agent.annotate("metric", _FINDINGS) == {}


async def test_annotate_unknown_kind_is_noop():
    agent = _agent('{"annotations": []}')
    assert await agent.annotate("not_a_kind", _FINDINGS) == {}


async def test_service_annotation_merge(monkeypatch):
    findings = [
        Finding(
            kind="metric",
            title="Metric from view",
            payload={"metric_name": "raw_name", "sql_expression": "SUM(orders.total_amount)"},
            evidence=[Evidence("view", "from v_monthly_revenue")],
            confidence=0.8,
        ),
        Finding(kind="fanout_warning", title="Fan-out", payload={"guidance": "g"}, confidence=0.7),
    ]
    provider = _FakeProvider(
        '{"annotations": [{"index": 0, "metric_name": "monthly_revenue", '
        '"display_name": "Monthly Revenue", "description": "desc"}]}'
    )
    monkeypatch.setattr("app.llm.provider_registry.get_provider", lambda *a, **k: provider)
    result = await compilation_service._annotate(findings)
    assert result[0].payload["metric_name"] == "monthly_revenue"
    assert result[0].payload["display_name"] == "Monthly Revenue"
    # structure untouched
    assert result[0].payload["sql_expression"] == "SUM(orders.total_amount)"


async def test_service_annotation_survives_missing_provider(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("no api key")

    monkeypatch.setattr("app.llm.provider_registry.get_provider", _raise)
    findings = [Finding(kind="metric", title="t", payload={"metric_name": "m"}, confidence=0.6)]
    result = await compilation_service._annotate(findings)
    assert result[0].payload["metric_name"] == "m"  # unchanged, no crash
