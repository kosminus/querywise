from app.core import telemetry
from app.core.telemetry import (
    bind_request_id,
    configure_logging,
    get_request_id,
)


def test_bind_and_get_request_id():
    rid = bind_request_id("abc123")
    assert rid == "abc123"
    assert get_request_id() == "abc123"


def test_bind_generates_id_when_absent():
    rid = bind_request_id(None)
    assert rid
    assert get_request_id() == rid


def test_configure_logging_console(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "log_format", "console")
    configure_logging()  # should not raise


def test_configure_logging_json(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "log_format", "json")
    configure_logging()  # should not raise


def test_configure_logging_without_structlog(monkeypatch):
    # Force the stdlib fallback path by hiding structlog.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "structlog":
            raise ImportError("structlog hidden for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    configure_logging()  # exercises _configure_stdlib without raising


def test_metrics_init_idempotent():
    # Safe to call repeatedly; returns a bool indicating prometheus availability.
    first = telemetry._init_metrics()
    second = telemetry._init_metrics()
    assert first == second
