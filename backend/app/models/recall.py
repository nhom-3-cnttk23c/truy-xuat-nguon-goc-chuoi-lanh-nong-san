"""Recall orders: an open recall blocks lot mutations; a completed recall
keeps blocking while its lots still carry an incident flag."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RecallOrder(Base):
    __tablename__ = "recall_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'completed')",
            name="ck_recall_orders_status_supported",
        ),
        CheckConstraint(
            "length(btrim(code)) > 0",
            name="ck_recall_orders_code_nonblank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_recall_orders_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default=text("'open'")
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_recall_orders_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecallOrderLot(Base):
    __tablename__ = "recall_order_lots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["recall_order_id"],
            ["recall_orders.id"],
            name="fk_recall_order_lots_recall_order_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["lot_id", "organization_id"],
            ["lots.id", "lots.organization_id"],
            name="fk_recall_order_lots_lot_same_org",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    recall_order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    incident_flag: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
