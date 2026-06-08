import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataPolicy(Base):
    """A governance rule enforced *before* a query reaches the connector.

    Connection-scoped (like the semantic layer). A policy applies to a request
    when the caller's role is in ``applies_to_roles`` (empty = all roles). When
    several policies apply they are merged most-restrictively into an effective
    policy (see ``policy_service.resolve_effective``):

    * ``max_rows`` / ``max_runtime_seconds`` — tightened to the minimum.
    * ``allowed_tables`` — a referenced table must appear in *every* non-empty
      allow-list (intersection); empty = no restriction.
    * ``blocked_tables`` / ``blocked_columns`` — union; referencing one blocks
      the query with an explanation.
    * ``masked_columns`` — union; values are redacted in the result.
    * ``row_filters`` — ``{table: "<sql boolean>"}``; injected as a row-level
      filter (AND-combined when multiple policies filter the same table).

    Table/column names may be bare (``email``) or schema/table-qualified
    (``public.users`` / ``users.email``).
    """

    __tablename__ = "data_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Lower numbers are reported first when explaining a block; does not change
    # the merge (which is always most-restrictive).
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # Roles this policy applies to (admin|editor|viewer). Empty = all roles.
    applies_to_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    max_rows: Mapped[int | None] = mapped_column(Integer)
    max_runtime_seconds: Mapped[int | None] = mapped_column(Integer)
    allowed_tables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    blocked_tables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    blocked_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    masked_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    row_filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
