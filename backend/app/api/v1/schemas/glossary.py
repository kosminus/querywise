from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GlossaryTermCreate(BaseModel):
    term: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1)
    sql_expression: str = Field(min_length=1)
    related_tables: list[str] = Field(default_factory=list)
    related_columns: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class GlossaryTermUpdate(BaseModel):
    term: str | None = Field(default=None, min_length=1, max_length=255)
    definition: str | None = Field(default=None, min_length=1)
    sql_expression: str | None = Field(default=None, min_length=1)
    related_tables: list[str] | None = None
    related_columns: list[str] | None = None
    examples: list[str] | None = None


class GlossaryTermResponse(BaseModel):
    id: UUID
    connection_id: UUID
    term: str
    definition: str
    sql_expression: str
    related_tables: list[str] | None
    related_columns: list[str] | None
    examples: list[str] | None
    status: str
    version: int
    certified_by_id: UUID | None
    certified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
