import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SavedQuery(Base):
    """A named, owned, re-runnable question + pinned SQL with typed parameters.

    Scoped by ``connection_id`` (the workspace cascade root) like the rest of
    the semantic layer; workspace isolation is enforced through the connection.
    """

    __tablename__ = "saved_queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    nl_question: Mapped[str | None] = mapped_column(Text)
    pinned_sql: Mapped[str] = mapped_column(Text, nullable=False)
    # List of param defs: {name, type: string|number|date|boolean, label, default}
    params: Mapped[list | None] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Phase 3 trust/lifecycle: draft|in_review|certified|deprecated.
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    certified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Visible to the whole workspace vs. owner-only.
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    connection: Mapped["DatabaseConnection"] = relationship()  # noqa: F821
    charts: Mapped[list["Chart"]] = relationship(  # noqa: F821
        back_populates="saved_query", cascade="all, delete-orphan"
    )
