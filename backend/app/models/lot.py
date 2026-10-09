from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.identity import Organization
from app.models.product import Product


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_lots_name_nonblank"),
        CheckConstraint(
            "quantity IS NULL OR (quantity > 0 AND quantity < 'Infinity'::numeric)",
            name="ck_lots_quantity_positive",
        ),
        CheckConstraint(
            "remaining_quantity >= 0 AND (quantity IS NULL OR remaining_quantity <= quantity)",
            name="ck_lots_remaining_quantity_range",
        ),
        CheckConstraint(
            "status IN ('active', 'pending_handover', 'closed')",
            name="ck_lots_status_supported",
        ),
        CheckConstraint(
            "parent_batch_id IS NULL OR parent_batch_id <> id",
            name="ck_lots_parent_not_self",
        ),
        ForeignKeyConstraint(
            ["farm_id", "organization_id"],
            ["farms.id", "farms.organization_id"],
            name="fk_lots_farm_same_organization",
            ondelete="RESTRICT",
        ),
        Index("ix_lots_organization_id", "organization_id"),
        Index(
            "ix_lots_holder_harvested_on",
            "current_holder_organization_id",
            "harvested_on",
            "id",
        ),
        Index(
            "ix_lots_holder_product_harvested",
            "current_holder_organization_id",
            "product_id",
            "harvested_on",
            "id",
        ),
        Index("ix_lots_farm_id", "farm_id"),
        Index("ix_lots_product_id", "product_id"),
        Index("ix_lots_organization_harvested_on", "organization_id", "harvested_on"),
        Index(
            "uq_lots_lot_code",
            "lot_code",
            unique=True,
        ),
        Index("ix_lots_parent_batch_id", "parent_batch_id"),
        Index("ix_lots_root_harvest_id_depth", "root_harvest_id", "lineage_depth"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_lots_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    current_holder_organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_lots_current_holder_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    farm_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lot_code: Mapped[str | None] = mapped_column(String(12))
    product_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "products.id", name="fk_lots_product_id_products", ondelete="RESTRICT"
        ),
    )
    harvested_on: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    remaining_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default=text("'active'")
    )
    parent_batch_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("lots.id", name="fk_lots_parent_batch_id_lots", ondelete="RESTRICT"),
    )
    lineage_depth: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )
    root_harvest_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    product: Mapped[Product | None] = relationship(lazy="joined")
    current_holder_organization: Mapped[Organization] = relationship(
        foreign_keys=[current_holder_organization_id], lazy="joined"
    )

    @property
    def current_holder_organization_name(self) -> str:
        return self.current_holder_organization.name
