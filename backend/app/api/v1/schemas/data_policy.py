from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DataPolicyBase(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 100
    applies_to_roles: list[str] = Field(
        default_factory=list, description="Roles this applies to (empty = all)"
    )
    max_rows: int | None = None
    max_runtime_seconds: int | None = None
    allowed_tables: list[str] = Field(default_factory=list)
    blocked_tables: list[str] = Field(default_factory=list)
    blocked_columns: list[str] = Field(default_factory=list)
    masked_columns: list[str] = Field(default_factory=list)
    row_filters: dict[str, str] = Field(
        default_factory=dict, description="table -> SQL boolean condition"
    )


class DataPolicyCreate(DataPolicyBase):
    pass


class DataPolicyUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    applies_to_roles: list[str] | None = None
    max_rows: int | None = None
    max_runtime_seconds: int | None = None
    allowed_tables: list[str] | None = None
    blocked_tables: list[str] | None = None
    blocked_columns: list[str] | None = None
    masked_columns: list[str] | None = None
    row_filters: dict[str, str] | None = None


class DataPolicyResponse(DataPolicyBase):
    id: UUID
    connection_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
