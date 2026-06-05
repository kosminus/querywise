from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.assistant import AssistantRequest, AssistantResponse
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import assistant_service

# Mounted under ``/query`` so it inherits the query rate limiter, and uses
# ``get_org_context`` like the other LLM query endpoints — the service resolves
# and authorizes the connection from the body.
router = APIRouter(prefix="/query", tags=["assistant"])


@router.post("/assistant", response_model=AssistantResponse)
async def assistant_turn(
    body: AssistantRequest,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """One conversational turn: classify the message and return ``{message, action?}``.

    ``action`` is either a ``sql_preview`` (confirm → run via /query/execute-sql) or a
    ``glossary_draft`` (confirm → create via /connections/{id}/glossary). The assistant
    itself never writes.
    """
    history = [m.model_dump() for m in body.history]
    result = await assistant_service.handle_turn(
        db, body.connection_id, body.message, history, ctx
    )
    return AssistantResponse(**result)
