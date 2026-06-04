"""Tracing helper tests.

When tracing is disabled (default) ``start_span`` is a no-op context manager.
When a tracer is configured, nested ``start_span`` calls produce nested spans —
this is what gives the query pipeline a single, well-structured trace.
"""

import pytest

from app.core import telemetry
from app.core.telemetry import start_span


def test_start_span_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(telemetry, "_tracer", None)
    with start_span("anything", foo="bar") as span:
        assert span is None


def test_configure_tracing_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "otel_enabled", False)
    monkeypatch.setattr(telemetry, "_tracing_ready", False)
    telemetry.configure_tracing()  # must not raise or set a tracer
    assert telemetry._tracer is None


def test_nested_spans_recorded():
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    original = telemetry._tracer
    telemetry.set_tracer(tracer)
    try:
        with start_span("parent", **{"k": "v"}):
            with start_span("child"):
                pass
    finally:
        telemetry.set_tracer(original)

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "parent" in names
    assert "child" in names

    parent = next(s for s in spans if s.name == "parent")
    child = next(s for s in spans if s.name == "child")
    # Child's parent span id is the parent's span id, and they share a trace.
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id
    assert parent.attributes.get("k") == "v"
