import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompilationRun(Base):
    """One semantic-layer-compiler execution against a connection."""

    __tablename__ = "compilation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued"
    )  # queued | running | completed | failed
    # Run options: llm_enabled, min_confidence, ignore_declared_fks, ...
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Per-kind finding counts + which evidence sources were available
    # (pg_stats / views / query_logs), so the UI can explain reduced confidence.
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    findings: Mapped[list["CompilationFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CompilationFinding(Base):
    """A proposed semantic object awaiting human review.

    ``payload`` is **name-keyed** (schema/table/column names, never cache ids):
    the schema cache is wiped on every re-introspect, so accepted findings are
    the durable source from which inferred relationships and dictionary entries
    are rematerialized. A finding becomes a real semantic object only when
    accepted — keeping unreviewed output away from the query-pipeline context
    builder (which retrieves draft metrics/glossary today).
    """

    __tablename__ = "compilation_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compilation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    # relationship | metric | dictionary | glossary | data_policy_row_filter |
    # data_policy_masking | dead_table | fanout_warning
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # List of {source, detail} facts, e.g.
    # {"source": "value_overlap", "detail": "98% of 500 sampled orders.customer_id ..."}
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="proposed"
    )  # proposed | accepted | dismissed
    created_entity_type: Mapped[str | None] = mapped_column(String(40))
    created_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["CompilationRun"] = relationship(back_populates="findings")
