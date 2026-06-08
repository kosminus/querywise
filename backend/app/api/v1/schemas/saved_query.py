from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ParamType = Literal["string", "number", "date", "boolean"]


class ParamDef(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: ParamType = "string"
    label: str | None = None
    default: Any | None = None


class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    nl_question: str | None = None
    pinned_sql: str = Field(min_length=1)
    params: list[ParamDef] = Field(default_factory=list)
    status: str = "draft"
    is_public: bool = False


class SavedQueryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    nl_question: str | None = None
    pinned_sql: str | None = Field(default=None, min_length=1)
    params: list[ParamDef] | None = None
    status: str | None = None
    is_public: bool | None = None


class SavedQueryResponse(BaseModel):
    id: UUID
    connection_id: UUID
    owner_id: UUID | None
    name: str
    description: str | None
    nl_question: str | None
    pinned_sql: str
    params: list[ParamDef] | None
    version: int
    status: str
    certified_by_id: UUID | None
    certified_at: datetime | None
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SavedQueryRunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    refresh: bool = False


class SavedQueryRunResponse(BaseModel):
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float | None
    cached: bool
    taken_at: datetime
