"""Unit tests for the notification adapters: factory fallback + deliver()."""

import app.notifications as notifications
from app.config import settings
from app.notifications import deliver, get_notifier
from app.notifications.email import EmailNotifier
from app.notifications.log import LogNotifier
from app.notifications.slack import SlackNotifier


def test_email_channel_falls_back_to_log_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert isinstance(get_notifier("email"), LogNotifier)


def test_email_channel_uses_email_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    assert isinstance(get_notifier("email"), EmailNotifier)


def test_slack_channel_falls_back_to_log_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "slack_webhook_url", None)
    assert isinstance(get_notifier("slack"), LogNotifier)


def test_slack_channel_uses_slack_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/x")
    assert isinstance(get_notifier("slack"), SlackNotifier)


def test_unknown_channel_is_log():
    assert isinstance(get_notifier("carrier-pigeon"), LogNotifier)


async def test_deliver_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)  # -> LogNotifier, always succeeds
    ok = await deliver("email", subject="hi", text_body="body", recipients=["a@b.c"])
    assert ok is True


async def test_deliver_swallows_failure_and_returns_false(monkeypatch):
    class BoomNotifier:
        async def send(self, message):
            raise RuntimeError("smtp down")

    monkeypatch.setattr(notifications, "get_notifier", lambda channel: BoomNotifier())
    ok = await deliver("email", subject="hi", text_body="body", recipients=["a@b.c"])
    assert ok is False
