from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ChartType = Literal["table", "line", "bar", "pie", "area", "scatter"]


class ChartCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    chart_type: ChartType
    config: dict = Field(default_factory=dict)


class ChartUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    chart_type: ChartType | None = None
    config: dict | None = None


class ChartResponse(BaseModel):
    id: UUID
    saved_query_id: UUID
    name: str
    chart_type: str
    config: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
