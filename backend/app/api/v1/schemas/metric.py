from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MetricCreate(BaseModel):
    metric_name: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sql_expression: str = Field(min_length=1)
    aggregation_type: str | None = None
    related_tables: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: dict | None = None


class MetricUpdate(BaseModel):
    metric_name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    sql_expression: str | None = Field(default=None, min_length=1)
    aggregation_type: str | None = None
    related_tables: list[str] | None = None
    dimensions: list[str] | None = None
    filters: dict | None = None


class MetricResponse(BaseModel):
    id: UUID
    connection_id: UUID
    metric_name: str
    display_name: str
    description: str | None
    sql_expression: str
    aggregation_type: str | None
    related_tables: list[str] | None
    dimensions: list[str] | None
    filters: dict | None
    status: str
    version: int
    certified_by_id: UUID | None
    certified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
