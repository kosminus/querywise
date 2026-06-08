from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.versioning_service import STATUSES


class StatusTransition(BaseModel):
    """Request body for a certification-lifecycle transition."""

    status: str = Field(description=f"Target status; one of: {', '.join(STATUSES)}")
    reason: str | None = None


class SemanticVersionResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    version: int
    status: str
    snapshot: dict[str, Any]
    change_reason: str | None
    changed_by_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
