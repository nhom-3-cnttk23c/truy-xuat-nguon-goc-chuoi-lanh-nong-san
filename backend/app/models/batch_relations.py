from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.transaction import Transaction


class BatchRelation(Base):
    """Immutable DAG edge linking parent to child lot(s) in split/merge operations."""

    __tablename__ = "batch_relations"
    __table_args__ = (
        CheckConstraint(
            "weight_transferred > 0",
            name="ck_batch_relations_weight_positive",
        ),
        CheckConstraint(
            "op_type IN ('split', 'merge')",
            name="ck_batch_relations_op_type",
        ),
        CheckConstraint(
            "parent_batch_id <> child_batch_id",
            name="ck_batch_relations_not_self_loop",
        ),
        Index("ix_batch_relations_parent", "parent_batch_id"),
        Index("ix_batch_relations_child", "child_batch_id"),
        Index("ix_batch_relations_transaction", "transaction_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    transaction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            name="fk_batch_relations_transaction_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    parent_batch_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_batch_relations_parent_batch_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    child_batch_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_batch_relations_child_batch_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    weight_transferred: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=3), nullable=False
    )
    op_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    transaction: Mapped[Transaction] = relationship(lazy="joined")
