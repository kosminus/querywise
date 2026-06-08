"""Slack notifier via an Incoming Webhook (uses the existing httpx dependency)."""

from __future__ import annotations

import httpx

from app.config import settings
from app.notifications.base import NotificationMessage, Notifier


class SlackNotifier(Notifier):
    channel = "slack"

    async def send(self, message: NotificationMessage) -> None:
        if not settings.slack_webhook_url:
            raise ValueError("Slack delivery requires SLACK_WEBHOOK_URL to be set.")
        # The webhook targets a fixed channel; render subject + body as text.
        text = f"*{message.subject}*\n{message.text_body}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(settings.slack_webhook_url, json={"text": text})
            resp.raise_for_status()
