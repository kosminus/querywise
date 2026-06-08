import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Artifact types whose SQL is parsed for table/column references.
ARTIFACT_SAVED_QUERY = "saved_query"
ARTIFACT_METRIC = "metric"
ARTIFACT_TYPES = (ARTIFACT_SAVED_QUERY, ARTIFACT_METRIC)

REF_TABLE = "table"
REF_COLUMN = "column"


class ArtifactDependency(Base):
    """A lineage edge: an artifact (saved query / metric) references a table/column.

    Recomputed from the artifact's SQL via ``lineage_service`` on create/update.
    Powers the catalog impact view ("what depends on this table") and the
    per-artifact "what this touches" view. Names are stored denormalized so the
    edge survives even if the schema cache hasn't been (re-)introspected;
    ``table_id`` / ``column_id`` are resolved best-effort when a match exists.
    """

    __tablename__ = "artifact_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ref_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    schema_name: Mapped[str | None] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255))
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cached_tables.id", ondelete="SET NULL")
    )
    column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cached_columns.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
