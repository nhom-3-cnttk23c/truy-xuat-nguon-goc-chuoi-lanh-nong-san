from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    """Immutable, append-only event record in the cold-chain agricultural traceability log."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(event_type)) > 0", name="ck_events_event_type_nonblank"
        ),
        CheckConstraint("sequence_number > 0", name="ck_events_sequence_positive"),
        CheckConstraint("length(prev_hash) = 64", name="ck_events_prev_hash_length"),
        CheckConstraint("length(event_hash) = 64", name="ck_events_event_hash_length"),
        UniqueConstraint("lot_id", "sequence_number", name="uq_events_lot_sequence"),
        UniqueConstraint("lot_id", "event_hash", name="uq_events_lot_event_hash"),
        Index("ix_events_organization_id", "organization_id"),
        Index("ix_events_lot_id", "lot_id"),
        Index("ix_events_recorded_at", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_events_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_events_lot_id_lots",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
