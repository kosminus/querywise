"""Integration tests for the NL → SQL → execute → interpret pipeline.

Unlike the other unit tests, these run ``query_service.execute_nl_query`` /
``execute_raw_sql`` end-to-end through the *real* agents (composer, validator,
error handler, interpreter), the real prompt plumbing, real policy
masking/limits, and the real audit/cost recording — substituting only the
process edges: a scripted LLM provider, a scripted connector, a fake DB
session, and a pre-built semantic context.
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError, SQLSafetyError
from app.db.models.audit_event import AuditEvent
from app.db.models.cost_attribution import CostAttribution
from app.db.models.query_history import QueryExecution
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.llm.base_provider import (
    BaseLLMProvider,
    LLMConfig,
    LLMProviderType,
    LLMResponse,
)
from app.semantic.context_builder import BuiltContext
from app.semantic.schema_linker import LinkedTable
from app.services import policy_service, query_service
from app.services.policy_service import MASK_TOKEN, EffectivePolicy

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeLLMProvider(BaseLLMProvider):
    """Returns scripted response payloads in order; records every call."""

    provider_type = LLMProviderType.ANTHROPIC

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list] = []

    async def complete(self, messages, config):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeLLMProvider ran out of scripted responses")
        return LLMResponse(
            content=self.responses.pop(0),
            model=config.model,
            input_tokens=10,
            output_tokens=10,
            finish_reason="stop",
            latency_ms=1.0,
        )

    async def stream(self, messages, config):  # pragma: no cover - unused
        yield ""

    async def generate_embedding(self, text):  # pragma: no cover - unused
        return [0.0]

    def list_models(self):  # pragma: no cover - unused
        return ["fake-model"]


class FakeConnector:
    """Yields scripted QueryResults or raises scripted exceptions, in order."""

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.executed_sql: list[str] = []
        self.limits: list[tuple[int, int]] = []

    async def execute_query(self, sql, params=None, timeout_seconds=30, max_rows=1000):
        self.executed_sql.append(sql)
        self.limits.append((max_rows, timeout_seconds))
        if not self.outcomes:
            raise AssertionError("FakeConnector ran out of scripted outcomes")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _NestedTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Just enough AsyncSession for history + audit + cost writes."""

    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def begin_nested(self):
        return _NestedTx()

    def of_type(self, cls):
        return [obj for obj in self.added if isinstance(obj, cls)]


def _query_result(columns, rows, **stats):
    from app.connectors.base_connector import QueryResult

    return QueryResult(
        columns=columns,
        column_types=["text"] * len(columns),
        rows=rows,
        row_count=len(rows),
        execution_time_ms=12.5,
        truncated=False,
        stats=dict(stats),
    )


# --------------------------------------------------------------------------- #
# Scripted LLM payloads (what each real agent will parse)
# --------------------------------------------------------------------------- #


def _compose(sql):
    return json.dumps(
        {
            "sql": sql,
            "explanation": "Lists exposures",
            "confidence": 0.9,
            "tables_used": ["exposures"],
            "assumptions": [],
        }
    )


def _fix(corrected_sql, should_retry=True):
    return json.dumps(
        {"corrected_sql": corrected_sql, "explanation": "fixed", "should_retry": should_retry}
    )


COMPOSE_OK = _compose("SELECT counterparty_name, exposure_amount FROM exposures LIMIT 10")
INTERPRET_OK = (
    '{"summary": "There are 2 exposures.", "highlights": ["ACME is largest"],'
    ' "suggested_followups": ["Break down by stage?"]}'
)


# --------------------------------------------------------------------------- #
# Fixtures: wire the pipeline's edges
# --------------------------------------------------------------------------- #

PROMPT_CONTEXT = "## DATABASE SCHEMA\nexposures(counterparty_name, exposure_amount)"


@pytest.fixture()
def ctx():
    return query_service.AuthContext(
        user=SimpleNamespace(id=uuid.uuid4()),
        organization_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        role="editor",
    )


@pytest.fixture()
def db():
    return FakeSession()


@pytest.fixture()
def pipeline(monkeypatch):
    """Patch the process edges; return a mutable harness the test configures."""
    harness = SimpleNamespace(provider=None, connector=None, policy=None)

    table = CachedTable(table_name="exposures", schema_name="public")
    columns = [
        CachedColumn(column_name="counterparty_name", data_type="text"),
        CachedColumn(column_name="exposure_amount", data_type="numeric"),
    ]
    context = BuiltContext(
        prompt_context=PROMPT_CONTEXT,
        tables=[LinkedTable(table=table, columns=columns, score=1.0, match_reason="keyword")],
        glossary=[],
        metrics=[],
        knowledge=[],
        dictionaries=[],
        sample_queries=[],
        question_embedding=None,
    )

    conn = SimpleNamespace(connector_type="postgresql", max_rows=1000, max_query_timeout_seconds=30)

    async def fake_get_connection(db, connection_id, ctx, **kw):
        return conn

    async def fake_build_context(db, connection_id, question, dialect="postgresql"):
        return context

    async def fake_get_or_create_connector(connection_id, connector_type, connection_string):
        return harness.connector

    async def fake_resolve_effective(db, connection_id, role):
        return harness.policy

    monkeypatch.setattr(query_service, "get_connection", fake_get_connection)
    monkeypatch.setattr(
        query_service, "get_decrypted_connection_string", lambda c: "postgresql://fake"
    )
    monkeypatch.setattr(query_service, "build_context", fake_build_context)
    monkeypatch.setattr(
        query_service, "route", lambda q: (harness.provider, LLMConfig(model="fake-model"))
    )
    monkeypatch.setattr(query_service, "get_or_create_connector", fake_get_or_create_connector)
    monkeypatch.setattr(policy_service, "resolve_effective", fake_resolve_effective)
    return harness


# --------------------------------------------------------------------------- #
# execute_nl_query — happy path
# --------------------------------------------------------------------------- #


async def test_happy_path_returns_results_and_records_history(pipeline, db, ctx):
    pipeline.provider = FakeLLMProvider([COMPOSE_OK, INTERPRET_OK])
    pipeline.connector = FakeConnector(
        [_query_result(["counterparty_name", "exposure_amount"], [["ACME", 100], ["Beta", 50]])]
    )

    result = await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    assert result["generated_sql"] == result["final_sql"]
    assert result["final_sql"].startswith("SELECT counterparty_name")
    assert result["rows"] == [["ACME", 100], ["Beta", 50]]
    assert result["summary"] == "There are 2 exposures."
    assert result["highlights"] == ["ACME is largest"]
    assert result["retry_count"] == 0
    assert result["llm_provider"] == "anthropic"

    # History row persisted as success, plus an audit event and a cost row.
    executions = db.of_type(QueryExecution)
    assert len(executions) == 1
    assert executions[0].execution_status == "success"
    assert executions[0].row_count == 2
    events = db.of_type(AuditEvent)
    assert [e.event_type for e in events] == ["query.executed"]
    assert len(db.of_type(CostAttribution)) == 1

    # Connector ran with the connection's limits.
    assert pipeline.connector.limits == [(1000, 30)]


async def test_composer_prompt_contains_semantic_context_and_question(pipeline, db, ctx):
    pipeline.provider = FakeLLMProvider([COMPOSE_OK, INTERPRET_OK])
    pipeline.connector = FakeConnector([_query_result(["a"], [[1]])])

    await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    composer_messages = pipeline.provider.calls[0]
    user_prompt = composer_messages[1].content
    assert PROMPT_CONTEXT in user_prompt
    assert "show exposures" in user_prompt


# --------------------------------------------------------------------------- #
# execute_nl_query — validation failure → error-handler repair
# --------------------------------------------------------------------------- #


async def test_invalid_sql_is_repaired_by_error_handler(pipeline, db, ctx):
    # Composer emits a non-SELECT statement; the validator rejects it and the
    # error handler must repair it before execution.
    bad = _compose("EXPLAIN SELECT * FROM exposures")
    fixed_sql = "SELECT counterparty_name FROM exposures"
    pipeline.provider = FakeLLMProvider([bad, _fix(fixed_sql), INTERPRET_OK])
    pipeline.connector = FakeConnector([_query_result(["counterparty_name"], [["ACME"]])])

    result = await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    assert result["generated_sql"].startswith("EXPLAIN")
    assert result["final_sql"] == fixed_sql
    assert result["retry_count"] == 1
    assert pipeline.connector.executed_sql == [fixed_sql]


async def test_unsafe_sql_surviving_retries_is_blocked_and_audited(pipeline, db, ctx):
    # Composer emits DML; the handler "fixes" it with more DML every time.
    # After 3 attempts the pipeline must refuse with 403 and audit the block.
    dml = _compose("DELETE FROM exposures")
    pipeline.provider = FakeLLMProvider(
        [dml, _fix("DELETE FROM exposures WHERE 1=1")] + [_fix("UPDATE exposures SET x=1")] * 2
    )
    pipeline.connector = FakeConnector([])

    with pytest.raises(AppError) as err:
        await query_service.execute_nl_query(db, uuid.uuid4(), "delete everything", ctx)

    assert err.value.status_code == 403
    events = db.of_type(AuditEvent)
    assert [e.event_type for e in events] == ["query.blocked"]
    assert pipeline.connector.executed_sql == []  # never reached the database


async def test_handler_giving_up_on_invalid_sql_raises_422(pipeline, db, ctx):
    bad = _compose("EXPLAIN SELECT 1")
    pipeline.provider = FakeLLMProvider([bad, _fix("", should_retry=False)])
    pipeline.connector = FakeConnector([])

    with pytest.raises(AppError) as err:
        await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    assert err.value.status_code == 422


# --------------------------------------------------------------------------- #
# execute_nl_query — execution failure → retry loop
# --------------------------------------------------------------------------- #


async def test_execution_error_is_retried_with_corrected_sql(pipeline, db, ctx):
    fixed_sql = "SELECT counterparty_name FROM exposures"
    pipeline.provider = FakeLLMProvider([COMPOSE_OK, _fix(fixed_sql), INTERPRET_OK])
    pipeline.connector = FakeConnector(
        [
            RuntimeError('column "exposure_amount" does not exist'),
            _query_result(["counterparty_name"], [["ACME"]]),
        ]
    )

    result = await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    assert result["retry_count"] == 1
    assert result["final_sql"] == fixed_sql
    assert len(pipeline.connector.executed_sql) == 2
    assert db.of_type(QueryExecution)[0].execution_status == "success"

    # The error handler must have seen the database error message.
    handler_prompt = pipeline.provider.calls[1][1].content
    assert "does not exist" in handler_prompt


async def test_execution_failing_all_retries_records_error_history(pipeline, db, ctx):
    pipeline.provider = FakeLLMProvider(
        [COMPOSE_OK] + [_fix(f"SELECT {i} FROM exposures") for i in range(3)]
    )
    pipeline.connector = FakeConnector([RuntimeError("relation missing")] * 4)

    with pytest.raises(AppError) as err:
        await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    assert "after 3 retries" in str(err.value)
    executions = db.of_type(QueryExecution)
    assert len(executions) == 1
    assert executions[0].execution_status == "error"
    assert executions[0].retry_count == 3
    assert len(pipeline.connector.executed_sql) == 4  # initial + 3 retries


# --------------------------------------------------------------------------- #
# execute_nl_query — policy limits + masking
# --------------------------------------------------------------------------- #


async def test_policy_masks_columns_and_tightens_limits(pipeline, db, ctx):
    pipeline.policy = EffectivePolicy(
        max_rows=10, max_runtime_seconds=5, masked_columns={"counterparty_name"}
    )
    pipeline.provider = FakeLLMProvider([COMPOSE_OK, INTERPRET_OK])
    pipeline.connector = FakeConnector(
        [_query_result(["counterparty_name", "exposure_amount"], [["ACME", 100]])]
    )

    result = await query_service.execute_nl_query(db, uuid.uuid4(), "show exposures", ctx)

    # Masked value never reaches the response…
    assert result["rows"] == [[MASK_TOKEN, 100]]
    # …or the interpreter LLM prompt.
    interpreter_prompt = pipeline.provider.calls[1][1].content
    assert "ACME" not in interpreter_prompt
    assert MASK_TOKEN in interpreter_prompt
    # Policy caps override the connection's looser limits (min wins).
    assert pipeline.connector.limits == [(10, 5)]


# --------------------------------------------------------------------------- #
# execute_raw_sql
# --------------------------------------------------------------------------- #


async def test_raw_sql_dml_is_blocked_and_audited(pipeline, db, ctx):
    with pytest.raises(SQLSafetyError):
        await query_service.execute_raw_sql(db, uuid.uuid4(), "DROP TABLE exposures", ctx)

    events = db.of_type(AuditEvent)
    assert [e.event_type for e in events] == ["query.blocked"]


async def test_raw_sql_happy_path_executes_without_llm_retry(pipeline, db, ctx):
    pipeline.provider = FakeLLMProvider([INTERPRET_OK])  # interpretation only
    pipeline.connector = FakeConnector([_query_result(["n"], [[1]])])

    result = await query_service.execute_raw_sql(
        db, uuid.uuid4(), "SELECT 1 AS n", ctx, original_question="how many?"
    )

    assert result["rows"] == [[1]]
    assert result["retry_count"] == 0
    assert result["summary"] == "There are 2 exposures."
    assert db.of_type(QueryExecution)[0].execution_status == "success"
