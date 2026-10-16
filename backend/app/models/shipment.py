"""Models for cold chain shipments and lot containment (N3-58)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Shipment(Base):
    """A cold transport shipment associating lots with a refrigerated container."""

    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_transit', 'completed')",
            name="ck_shipments_status_supported",
        ),
        CheckConstraint(
            "length(btrim(shipment_code)) > 0",
            name="ck_shipments_code_nonblank",
        ),
        CheckConstraint(
            "length(btrim(container_code)) > 0",
            name="ck_shipments_container_nonblank",
        ),
        CheckConstraint(
            "(status = 'in_transit' AND completed_at IS NULL) OR (status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_shipments_completion_status",
        ),
        Index("ix_shipments_organization_id", "organization_id"),
        Index("ix_shipments_status", "status"),
        Index("ix_shipments_container_code", "container_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    shipment_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_shipments_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_shipments_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    container_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="in_transit",
        server_default=text("'in_transit'"),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    shipment_lots = relationship(
        "ShipmentLot",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentLot.loaded_at",
    )


class ShipmentLot(Base):
    """Association linking an active lot to a cold shipment."""

    __tablename__ = "shipment_lots"
    __table_args__ = (
        UniqueConstraint("shipment_id", "lot_id", name="uq_shipment_lots_shipment_lot"),
        Index("ix_shipment_lots_shipment_id", "shipment_id"),
        Index("ix_shipment_lots_lot_id", "lot_id"),
        # NFR (N3-58): một lô chỉ nằm trong một chuyến đang chạy tại một thời điểm
        Index(
            "uq_shipment_lots_active_lot",
            "lot_id",
            unique=True,
            postgresql_where=text("unloaded_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    shipment_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "shipments.id",
            name="fk_shipment_lots_shipment_id_shipments",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    lot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "lots.id",
            name="fk_shipment_lots_lot_id_lots",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    unloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    shipment = relationship("Shipment", back_populates="shipment_lots")
    lot = relationship("Lot", foreign_keys=[lot_id])
