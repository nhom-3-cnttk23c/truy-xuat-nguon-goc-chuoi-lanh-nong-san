"""Schemas for cold chain shipments and lot containment (N3-58)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ShipmentCreate(BaseModel):
    """Payload to declare a new cold shipment with lots and a refrigerated container."""

    container_code: str = Field(..., min_length=2, max_length=64)
    lot_ids: list[UUID] = Field(..., min_length=1)
    notes: str | None = Field(default=None, max_length=500)
    shipment_code: str | None = Field(default=None, max_length=32)

    @field_validator("container_code")
    @classmethod
    def validate_container_code(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Mã thùng lạnh là bắt buộc.")
        return trimmed

    @field_validator("lot_ids")
    @classmethod
    def validate_lot_ids(cls, value: list[UUID]) -> list[UUID]:
        if not value:
            raise ValueError("Chuyến vận chuyển phải có ít nhất một lô hàng.")
        if len(value) != len(set(value)):
            raise ValueError("Danh sách lô hàng không được chứa lô trùng lặp.")
        return value


class ShipmentLotItemRead(BaseModel):
    """Projection of a lot assigned to a shipment."""

    model_config = ConfigDict(from_attributes=True)

    lot_id: UUID
    lot_code: str | None = None
    name: str | None = None
    quantity: str | None = None
    remaining_quantity: str | None = None
    status: str | None = None
    loaded_at: datetime
    unloaded_at: datetime | None = None


class ShipmentRead(BaseModel):
    """Summary projection of a cold chain shipment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shipment_code: str
    organization_id: UUID
    created_by_user_id: UUID
    container_code: str
    status: str
    notes: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    lot_count: int = 0


class ShipmentDetailRead(ShipmentRead):
    """Detailed projection of a shipment including its assigned lots."""

    lots: list[ShipmentLotItemRead] = Field(default_factory=list)
