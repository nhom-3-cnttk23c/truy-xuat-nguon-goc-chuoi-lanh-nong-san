from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.transaction import Transaction


class BatchEvent(Base):
    """Immutable, append-only event record for lot split/merge operations.

    Like Event, but specifically for tracking lineage operations (split, merge).
    Enforced immutable at DB level with BEFORE UPDATE/DELETE triggers.
    """

    __tablename__ = "batch_events"
    __table_args__ = (
        CheckConstraint("length(event_type) > 0", name="ck_batch_events_event_type"),
        CheckConstraint("length(prev_hash) = 64", name="ck_batch_events_prev_hash_len"),
        CheckConstraint("length(hash) = 64", name="ck_batch_events_hash_len"),
        UniqueConstraint("batch_id", "event_id", name="uq_batch_events_batch_event_id"),
        UniqueConstraint("batch_id", "hash", name="uq_batch_events_batch_hash"),
        Index("ix_batch_events_batch_id", "batch_id"),
        Index("ix_batch_events_actor_user_id", "actor_user_id"),
        Index("ix_batch_events_recorded_at", "recorded_at"),
    )

    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    batch_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_batch_events_batch_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_batch_events_actor_user_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    transaction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            name="fk_batch_events_transaction_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    transaction: Mapped[Transaction] = relationship(lazy="joined")
