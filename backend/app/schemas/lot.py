from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.product import ProductRead


class LotCreate(BaseModel):
    farm_id: UUID
    product_id: UUID
    harvested_on: date
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_finite_quantity(cls, value: object) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("Khối lượng phải lớn hơn 0.")
        try:
            quantity = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("Khối lượng phải là một số hợp lệ.") from error
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Khối lượng phải lớn hơn 0.")
        return quantity

    @field_validator("harvested_on")
    @classmethod
    def validate_harvest_date(cls, harvested_on: date) -> date:
        vietnam_time = timezone(timedelta(hours=7))
        local_today = datetime.now(vietnam_time).date()
        if harvested_on > local_today:
            raise ValueError("Ngày thu hoạch không được ở tương lai.")
        return harvested_on


class LotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    farm_id: UUID
    name: str
    lot_code: str | None = None
    product_id: UUID | None = None
    harvested_on: date | None = None
    quantity: Decimal | None = None
    remaining_quantity: Decimal
    current_holder_organization_id: UUID
    current_holder_organization_name: str
    status: str
    parent_batch_id: UUID | None = None
    lineage_depth: int = 0
    root_harvest_id: UUID | None = None
    product: ProductRead | None = None


class LotListRead(BaseModel):
    items: list[LotRead]
    next_cursor: str | None
