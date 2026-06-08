import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DashboardTile(Base):
    """A single tile on a dashboard: a saved query rendered as a chart or table."""

    __tablename__ = "dashboard_tiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False
    )
    # The data source. A tile can't function without its query, so deleting the
    # saved query removes its tiles.
    saved_query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_queries.id", ondelete="CASCADE"), nullable=False
    )
    # Optional visualization; null = render as a table.
    chart_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charts.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(255))
    # react-grid-layout position: {x, y, w, h}
    position: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    # Auto-refresh interval in seconds; null = manual refresh only.
    refresh_interval: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dashboard: Mapped["Dashboard"] = relationship(back_populates="tiles")  # noqa: F821
