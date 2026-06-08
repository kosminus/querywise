from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.v1.schemas.saved_query import ParamDef

# A dashboard filter is shaped like a saved-query parameter; its value is passed
# to each tile's run and consumed only by tiles whose SQL references {{name}}.
DashboardFilter = ParamDef


class TilePosition(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 6


class DashboardTileCreate(BaseModel):
    saved_query_id: UUID
    chart_id: UUID | None = None
    title: str | None = None
    position: TilePosition = Field(default_factory=TilePosition)
    refresh_interval: int | None = None


class DashboardTileUpdate(BaseModel):
    chart_id: UUID | None = None
    title: str | None = None
    position: TilePosition | None = None
    refresh_interval: int | None = None


class DashboardTileResponse(BaseModel):
    id: UUID
    dashboard_id: UUID
    saved_query_id: UUID
    chart_id: UUID | None
    title: str | None
    position: dict | None
    refresh_interval: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    filters: list[DashboardFilter] = Field(default_factory=list)
    is_public: bool = False


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    filters: list[DashboardFilter] | None = None
    is_public: bool | None = None


class DashboardResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    owner_id: UUID | None
    name: str
    description: str | None
    filters: list[DashboardFilter] | None
    is_public: bool
    tiles: list[DashboardTileResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TileLayoutItem(BaseModel):
    tile_id: UUID
    x: int
    y: int
    w: int
    h: int


class TileLayoutUpdate(BaseModel):
    layout: list[TileLayoutItem]


class TileRunRequest(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


class TileRunResponse(BaseModel):
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float | None
    cached: bool
    taken_at: datetime
    # Present when the tile has an associated chart.
    chart_type: str | None = None
    chart_config: dict | None = None
