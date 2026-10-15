"""Model for recall orders."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RecallOrder(Base):
    __tablename__ = "recall_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'completed')",
            name="ck_recall_orders_status_supported",
        ),
        CheckConstraint(
            "length(btrim(recall_code)) > 0",
            name="ck_recall_orders_code_nonblank",
        ),
        CheckConstraint(
            "length(btrim(reason)) >= 20",
            name="ck_recall_orders_reason_min_length",
        ),
        Index("ix_recall_orders_root_lot_id", "root_lot_id"),
        Index("ix_recall_orders_status", "status"),
        Index("ix_recall_orders_opened_by_org_id", "opened_by_organization_id"),
        Index(
            "uq_recall_orders_open_root_lot",
            "root_lot_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    recall_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    root_lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_recall_orders_root_lot_id_lots",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    opened_by_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_recall_orders_opened_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    opened_by_organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_recall_orders_opened_by_org_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="open", server_default=text("'open'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Helper alias
    @property
    def code(self) -> str:
        return self.recall_code

    # Relationships
    root_lot = relationship("Lot", foreign_keys=[root_lot_id])
    opened_by_user = relationship("User", foreign_keys=[opened_by_user_id])
    opened_by_organization = relationship(
        "Organization", foreign_keys=[opened_by_organization_id]
    )
