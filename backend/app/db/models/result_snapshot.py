import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResultSnapshot(Base):
    """A persisted query result — doubles as the result cache.

    A cache hit is the newest snapshot for a given ``sql_hash`` within the
    freshness window (``RESULT_CACHE_TTL_SECONDS``). ``sql_hash`` is
    ``sha256(final_sql + json(params_used) + connection_id)``.
    """

    __tablename__ = "result_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    saved_query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_queries.id", ondelete="SET NULL")
    )
    sql_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    columns: Mapped[list | None] = mapped_column(JSONB, default=list)
    column_types: Mapped[list | None] = mapped_column(JSONB, default=list)
    rows: Mapped[list | None] = mapped_column(JSONB, default=list)
    row_count: Mapped[int | None] = mapped_column(Integer)
    params_used: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    execution_time_ms: Mapped[float | None] = mapped_column(Float)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_result_snapshots_sql_hash_taken_at", "sql_hash", text("taken_at DESC")),
    )
