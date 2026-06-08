"""Notification delivery seam.

A ``Notifier`` turns a :class:`NotificationMessage` into a delivered message on
one channel (email, Slack, …). Adapters degrade gracefully: when a channel is
not configured, the factory returns :class:`~app.notifications.log.LogNotifier`
so callers (scheduled reports, magic-link delivery) keep working in dev without
SMTP/Slack credentials — mirroring the pre-Phase-4 "log the token" behaviour.

``send`` raises on a hard delivery failure so the caller can record it; callers
that must never fail (e.g. fire-and-forget) wrap the call themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NotificationMessage:
    subject: str
    text_body: str
    html_body: str | None = None
    # Channel-specific destinations (email addresses for email; ignored by
    # Slack, which targets the configured webhook's channel).
    recipients: list[str] = field(default_factory=list)


class Notifier(ABC):
    """Delivers a message on one channel."""

    channel: str = "base"

    @abstractmethod
    async def send(self, message: NotificationMessage) -> None:
        """Deliver ``message``. Raises on hard failure."""
