import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompilationRunCreate(BaseModel):
    llm_enabled: bool = True
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # Eval mode: pretend declared FKs don't exist so join inference is exercised.
    ignore_declared_fks: bool = False


class CompilationProgressResponse(BaseModel):
    total: int
    completed: int
    stage: str
    status: str
    error: str | None = None


class CompilationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connection_id: uuid.UUID
    status: str
    options: dict
    stats: dict
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    progress: CompilationProgressResponse | None = None


class CompilationFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    connection_id: uuid.UUID
    kind: str
    title: str
    payload: dict
    evidence: list
    confidence: float
    status: str
    created_entity_type: str | None
    created_entity_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class BulkReviewRequest(BaseModel):
    finding_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(accept|dismiss)$")


class BulkReviewResponse(BaseModel):
    succeeded: int
    failed: int
