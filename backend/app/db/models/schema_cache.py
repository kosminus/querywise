import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db.base import Base


class CachedTable(Base):
    __tablename__ = "cached_tables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "table" | "view"
    comment: Mapped[str | None] = mapped_column(Text)
    row_count_estimate: Mapped[int | None] = mapped_column(Integer)
    description_embedding = mapped_column(Vector(settings.embedding_dimension), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    connection: Mapped["DatabaseConnection"] = relationship(back_populates="tables")  # noqa: F821
    columns: Mapped[list["CachedColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )
    outgoing_relationships: Mapped[list["CachedRelationship"]] = relationship(
        foreign_keys="CachedRelationship.source_table_id",
        back_populates="source_table",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["CachedRelationship"]] = relationship(
        foreign_keys="CachedRelationship.target_table_id",
        back_populates="target_table",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        {"schema": None},  # Default schema
    )


class CachedColumn(Base):
    __tablename__ = "cached_columns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cached_tables.id", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    description_embedding = mapped_column(Vector(settings.embedding_dimension), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    table: Mapped["CachedTable"] = relationship(back_populates="columns")
    dictionary_entries: Mapped[list["DictionaryEntry"]] = relationship(  # noqa: F821
        back_populates="column", cascade="all, delete-orphan"
    )


class CachedRelationship(Base):
    __tablename__ = "cached_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    constraint_name: Mapped[str | None] = mapped_column(String(255))
    # 'fk' = declared foreign key (re-derived on every introspect);
    # 'inferred' = compiler-accepted edge (rematerialized from accepted findings).
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="fk")
    confidence: Mapped[float | None] = mapped_column(Float)
    cardinality: Mapped[str | None] = mapped_column(String(10))  # '1:1'|'N:1'|'1:N'|'N:N'
    evidence = mapped_column(JSONB, nullable=True)
    source_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cached_tables.id", ondelete="CASCADE"), nullable=False
    )
    source_column: Mapped[str] = mapped_column(String(255), nullable=False)
    target_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cached_tables.id", ondelete="CASCADE"), nullable=False
    )
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_table: Mapped["CachedTable"] = relationship(
        foreign_keys=[source_table_id], back_populates="outgoing_relationships"
    )
    target_table: Mapped["CachedTable"] = relationship(
        foreign_keys=[target_table_id], back_populates="incoming_relationships"
    )
