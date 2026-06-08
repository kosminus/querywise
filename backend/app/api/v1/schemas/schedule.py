from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.schedule import TARGET_TYPES


class ScheduleThreshold(BaseModel):
    metric: str = Field("row_count", description="'row_count' or a result column name")
    op: str = Field(">", description="One of: > >= < <= == !=")
    value: float


class ScheduleCreate(BaseModel):
    name: str
    target_type: str = Field(description=f"One of: {', '.join(TARGET_TYPES)}")
    target_id: UUID
    cron: str = Field(description="5-field cron expression (UTC)")
    channel: str = Field("email", description="email | slack | log")
    recipients: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    threshold: ScheduleThreshold | None = None
    only_on_threshold: bool = False
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron: str | None = None
    channel: str | None = None
    recipients: list[str] | None = None
    params: dict[str, Any] | None = None
    threshold: ScheduleThreshold | None = None
    only_on_threshold: bool | None = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    id: UUID
    name: str
    target_type: str
    target_id: UUID
    cron: str
    channel: str
    recipients: list[str]
    params: dict[str, Any]
    threshold: dict[str, Any] | None
    only_on_threshold: bool
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduleRunResponse(BaseModel):
    schedule_id: UUID
    status: str
    delivered: bool
    threshold_met: bool | None
    error: str | None
