import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CostAttribution(Base):
    """Per-execution cost + usage stats, attributed to a workspace/user.

    Written best-effort after each query execution (post-hoc, since warehouse
    job stats are only available once the query completes). Powers the usage
    analytics dashboards (slowest queries, error rate, most-queried tables, cost
    per team). ``cost_usd`` is an estimate from the configured pricing model;
    ``scanned_bytes`` / ``slot_ms`` / ``dbu`` are populated when the connector
    reports them (BigQuery today), else null.
    """

    __tablename__ = "cost_attributions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL")
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    query_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_executions.id", ondelete="SET NULL")
    )

    source_provider: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    execution_time_ms: Mapped[float | None] = mapped_column(Float)
    row_count: Mapped[int | None] = mapped_column(Integer)
    scanned_bytes: Mapped[int | None] = mapped_column(Integer)
    slot_ms: Mapped[int | None] = mapped_column(Integer)
    dbu: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Referenced tables ("schema.table" or "table"), for most-queried analytics.
    tables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
