import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DatabaseConnection(Base):
    __tablename__ = "database_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Identity scoping (Phase 1). organization_id is SaaS-ready; workspace_id
    # (a Team) is the isolation unit and the cascade root for all metadata.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Private connections are visible only to their owner within the workspace.
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Connection string stored encrypted; handled at service layer
    connection_string_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    default_schema: Mapped[str] = mapped_column(String(255), default="public")
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    max_query_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_rows: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_introspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tables: Mapped[list["CachedTable"]] = relationship(  # noqa: F821
        back_populates="connection", cascade="all, delete-orphan"
    )
    glossary_terms: Mapped[list["GlossaryTerm"]] = relationship(  # noqa: F821
        back_populates="connection", cascade="all, delete-orphan"
    )
    metric_definitions: Mapped[list["MetricDefinition"]] = relationship(  # noqa: F821
        back_populates="connection", cascade="all, delete-orphan"
    )
    sample_queries: Mapped[list["SampleQuery"]] = relationship(  # noqa: F821
        back_populates="connection", cascade="all, delete-orphan"
    )
