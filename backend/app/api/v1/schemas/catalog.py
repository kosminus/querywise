from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CatalogHitResponse(BaseModel):
    type: str
    id: str
    name: str
    description: str | None = None
    status: str | None = None
    certified_at: datetime | None = None
    owner_id: str | None = None
    context: str | None = None
    score: float
    match_reason: str

    model_config = {"from_attributes": True}


class CatalogFacetsResponse(BaseModel):
    schemas: list[str]
    owners: list[str]
    tags: list[str]
    types: list[str]
    status_counts: dict[str, int]


class LineageRefResponse(BaseModel):
    id: UUID
    artifact_type: str
    artifact_id: UUID
    ref_kind: str
    schema_name: str | None
    table_name: str
    column_name: str | None
    table_id: UUID | None
    column_id: UUID | None

    model_config = {"from_attributes": True}
