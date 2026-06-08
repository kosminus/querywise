import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import (
    AuthProviderInfo,
    LoginRequest,
    MagicLinkRequest,
    MagicLinkResponse,
    MagicLinkVerifyRequest,
    MeResponse,
    RegisterRequest,
    UserResponse,
    WorkspaceMembershipResponse,
)
from app.config import settings
from app.core.auth import clear_session_cookie, get_current_user, set_session_cookie
from app.core.auth_providers import get_auth_provider
from app.db.models.user import User
from app.db.session import get_db
from app.notifications import deliver
from app.services import auth_service, identity_service

logger = logging.getLogger("querywise.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _login(response: Response, user: User) -> UserResponse:
    set_session_cookie(response, auth_service.issue_session_token(user))
    return UserResponse.model_validate(user)


@router.get("/providers", response_model=AuthProviderInfo)
async def auth_providers():
    """Advertise the configured login method so the frontend renders the right UI."""
    provider = get_auth_provider()
    return AuthProviderInfo(**provider.describe(), disable_auth=settings.disable_auth)


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate_password(db, body.email, body.password)
    return _login(response, user)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register_user(db, body.email, body.password, body.name)
    return _login(response, user)


@router.post("/magic-link", response_model=MagicLinkResponse)
async def request_magic_link(body: MagicLinkRequest, db: AsyncSession = Depends(get_db)):
    token = await auth_service.request_magic_link(db, body.email)
    base = settings.app_base_url or (settings.cors_origins[0] if settings.cors_origins else None)
    verify_url = f"{base}/login/verify?token={token}" if base else None

    # Deliver via the configured channel (Phase 4). With no SMTP host set this
    # degrades to logging — so local dev still completes the flow.
    await deliver(
        "email",
        subject="Your QueryWise sign-in link",
        text_body=(
            f"Click to sign in: {verify_url}\n\n"
            f"This link expires in {settings.magic_link_ttl_minutes} minutes."
            if verify_url
            else f"Your sign-in token: {token}"
        ),
        recipients=[body.email],
    )
    # Outside production, also surface the token so a dev client can complete login.
    expose = settings.environment != "production"
    return MagicLinkResponse(
        sent=True,
        dev_token=token if expose else None,
        dev_verify_url=verify_url if expose else None,
    )


@router.post("/magic-link/verify", response_model=UserResponse)
async def verify_magic_link(
    body: MagicLinkVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.verify_magic_link(db, body.token)
    return _login(response, user)


@router.post("/logout", status_code=204)
async def logout(response: Response):
    clear_session_cookie(response)


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memberships = await identity_service.list_my_memberships(db, user)
    return MeResponse(
        user=UserResponse.model_validate(user),
        workspaces=[
            WorkspaceMembershipResponse(
                team_id=m.team_id, team_name=m.team.name, role=m.role
            )
            for m in memberships
        ],
    )
