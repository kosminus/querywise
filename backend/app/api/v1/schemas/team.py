from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.membership import ROLES


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TeamResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="viewer")


class MembershipResponse(BaseModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    user_email: str
    user_name: str | None
    role: str
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    # The plaintext key — returned exactly once, on creation.
    key: str


# Re-exported so endpoints can validate role values against the model layer.
VALID_ROLES = ROLES
