from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    source_url: str | None = None


class FetchUrlRequest(BaseModel):
    url: str = Field(min_length=1)


class FetchUrlResponse(BaseModel):
    title: str | None
    content: str


class KnowledgeChunkResponse(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    connection_id: UUID
    title: str
    source_url: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentDetail(KnowledgeDocumentResponse):
    chunks: list[KnowledgeChunkResponse]
