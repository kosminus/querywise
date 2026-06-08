from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: UUID
    event_type: str
    actor_id: UUID | None
    workspace_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
