import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Dashboard(Base):
    """A workspace-shared grid of tiles composed from saved queries.

    Unlike the connection-scoped artifacts (saved queries, charts), a dashboard
    composes tiles that may draw on saved queries from different connections in
    the same workspace, so it is scoped directly by ``workspace_id``.
    """

    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # List of filter defs {name, type, label, default} — same shape as a saved-query ParamDef.
    # Values are passed to each tile's run; a tile only consumes the filters its SQL references.
    filters: Mapped[list | None] = mapped_column(JSONB, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tiles: Mapped[list["DashboardTile"]] = relationship(  # noqa: F821
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardTile.created_at",
    )
