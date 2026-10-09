from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.identity import Organization, User


class Transaction(Base):
    """Atomic transaction boundary for split/merge lot operations."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "op_type IN ('split', 'merge')",
            name="ck_transactions_op_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'committed', 'rolled_back')",
            name="ck_transactions_status",
        ),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    initiator_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_transactions_initiator_user_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    initiator_organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_transactions_initiator_organization_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    op_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="'pending'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    initiator_user: Mapped[User] = relationship(lazy="joined")
    initiator_organization: Mapped[Organization] = relationship(lazy="joined")
