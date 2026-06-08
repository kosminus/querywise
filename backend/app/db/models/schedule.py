import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# What a schedule runs.
TARGET_SAVED_QUERY = "saved_query"
TARGET_DASHBOARD = "dashboard"
TARGET_TYPES = (TARGET_SAVED_QUERY, TARGET_DASHBOARD)

# Last-run outcome.
STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"  # ran but delivery suppressed (threshold not met)


class Schedule(Base):
    """A recurring report: run a saved query or dashboard on a cron schedule and
    deliver the result over a notification channel.

    Workspace-scoped (like :class:`Dashboard`). ``next_run_at`` is computed from
    ``cron`` and is the column the scheduler claims on; ``last_*`` capture the
    most recent run for display + audit.
    """

    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Standard 5-field cron expression (UTC).
    cron: Mapped[str] = mapped_column(String(120), nullable=False)
    # Delivery channel: "email" | "slack" | "log".
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    recipients: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Params supplied to the saved query / dashboard filters at run time.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Optional alert-on-threshold: {"metric": "row_count"|"<column>",
    # "op": ">"|">="|"<"|"<="|"=="|"!=", "value": <number>}.
    threshold: Mapped[dict | None] = mapped_column(JSONB)
    # When true, deliver only if the threshold is met (otherwise mark skipped).
    only_on_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
