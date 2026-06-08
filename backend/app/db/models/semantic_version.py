import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Semantic entity types that carry a certification lifecycle + version history.
ENTITY_METRIC = "metric"
ENTITY_GLOSSARY = "glossary"
ENTITY_SAMPLE_QUERY = "sample_query"
ENTITY_SAVED_QUERY = "saved_query"
ENTITY_TYPES = (ENTITY_METRIC, ENTITY_GLOSSARY, ENTITY_SAMPLE_QUERY, ENTITY_SAVED_QUERY)


class SemanticVersion(Base):
    """An append-only snapshot of a semantic entity at a given version.

    Written on every content edit and status transition, giving each metric /
    glossary term / sample query / saved query a changelog + diff history with the
    reviewer and reason. Scoped by ``connection_id`` (the workspace cascade root)
    like the entities it snapshots.
    """

    __tablename__ = "semantic_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Full serialized entity fields at this version.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
