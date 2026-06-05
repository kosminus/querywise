from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# A pragmatic email pattern — full RFC validation would pull in email-validator;
# we keep deps light and rely on a length/format-bounded string.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=256)
    name: str | None = Field(default=None, max_length=255)


class MagicLinkRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_PATTERN)


class MagicLinkVerifyRequest(BaseModel):
    token: str = Field(min_length=1)


class MagicLinkResponse(BaseModel):
    sent: bool
    # Surfaced only in non-production so local dev can complete the flow.
    dev_token: str | None = None
    dev_verify_url: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str | None
    status: str
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMembershipResponse(BaseModel):
    team_id: UUID
    team_name: str
    role: str


class MeResponse(BaseModel):
    user: UserResponse
    workspaces: list[WorkspaceMembershipResponse]


class AuthProviderInfo(BaseModel):
    name: str
    supports_password: bool
    supports_magic_link: bool
    is_sso: bool
    disable_auth: bool
