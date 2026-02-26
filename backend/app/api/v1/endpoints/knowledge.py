import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas.knowledge import (
    FetchUrlRequest,
    FetchUrlResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDetail,
    KnowledgeDocumentResponse,
)
from app.core.exceptions import NotFoundError
from app.db.models.knowledge import KnowledgeDocument
from app.db.session import get_db
from app.services.knowledge_service import (
    _clean_html,
    _split_sections,
    import_document,
)

router = APIRouter(tags=["knowledge"])


@router.get(
    "/connections/{connection_id}/knowledge",
    response_model=list[KnowledgeDocumentResponse],
)
async def list_knowledge_documents(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.connection_id == connection_id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/connections/{connection_id}/knowledge",
    response_model=KnowledgeDocumentResponse,
    status_code=201,
)
async def create_knowledge_document(
    connection_id: uuid.UUID,
    body: KnowledgeDocumentCreate,
    db: AsyncSession = Depends(get_db),
):
    doc = await import_document(
        db,
        connection_id=connection_id,
        title=body.title,
        content=body.content,
        source_url=body.source_url,
    )
    return doc


@router.get(
    "/connections/{connection_id}/knowledge/{document_id}",
    response_model=KnowledgeDocumentDetail,
)
async def get_knowledge_document(
    connection_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == document_id)
        .options(selectinload(KnowledgeDocument.chunks))
    )
    doc = result.scalar_one_or_none()
    if not doc or doc.connection_id != connection_id:
        raise NotFoundError("KnowledgeDocument", str(document_id))
    return doc


@router.delete(
    "/connections/{connection_id}/knowledge/{document_id}",
    status_code=204,
)
async def delete_knowledge_document(
    connection_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(KnowledgeDocument, document_id)
    if not doc or doc.connection_id != connection_id:
        raise NotFoundError("KnowledgeDocument", str(document_id))
    await db.delete(doc)
    await db.flush()


@router.post(
    "/knowledge/fetch-url",
    response_model=FetchUrlResponse,
)
async def fetch_url_content(body: FetchUrlRequest):
    """Fetch a URL and return its text content (HTML is parsed to plain text)."""
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; QueryWise/1.0)",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=headers
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Remote server returned {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch URL: {exc}",
        ) from exc

    html = resp.text
    cleaned = _clean_html(html)
    title, sections = _split_sections(cleaned)

    # Combine all section texts into one block for the textarea
    parts: list[str] = []
    for section_path, section_text in sections:
        if section_path:
            parts.append(f"## {section_path}\n")
        parts.append(section_text)
        parts.append("")
    content = "\n".join(parts).strip()

    return FetchUrlResponse(title=title, content=content)
