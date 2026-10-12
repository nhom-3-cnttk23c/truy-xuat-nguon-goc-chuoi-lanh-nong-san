from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.farm import FarmRead
from app.schemas.lot import LotCreate, LotRead

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


class SplitChild(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: Quantity
    location_id: UUID | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def finite_quantity(cls, value: object) -> Decimal:
        return LotCreate.validate_finite_quantity(value)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Tên lô không được để trống.")
        return value.strip()


class LotSplit(BaseModel):
    children: list[SplitChild] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class MergeParent(BaseModel):
    lot_id: UUID
    quantity: Quantity

    @field_validator("quantity", mode="before")
    @classmethod
    def finite_quantity(cls, value: object) -> Decimal:
        return LotCreate.validate_finite_quantity(value)


class LotMerge(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parents: list[MergeParent] = Field(min_length=2, max_length=100)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return SplitChild.trim_name(value)

    @model_validator(mode="after")
    def unique_parents(self):
        if len({parent.lot_id for parent in self.parents}) != len(self.parents):
            raise ValueError("Mỗi lô mẹ chỉ được chọn một lần.")
        return self


class SplitRead(BaseModel):
    parent: LotRead
    children: list[LotRead]


class RelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    parent_lot_id: UUID
    child_lot_id: UUID
    quantity: Decimal
    operation: str


class GraphLotRead(LotRead):
    remaining_quantity: Decimal | None
    current_holder_organization_id: UUID | None
    current_holder_organization_name: str | None
    historical_only: bool = False


class LineageRead(BaseModel):
    selected_lot_id: UUID
    direction: str
    nodes: list[GraphLotRead]
    edges: list[RelationRead]
    roots: list[UUID]
    root_farms: list[FarmRead]


class LotDetailRead(LotRead):
    parents: list[GraphLotRead]
    children: list[GraphLotRead]
    direct_farms: list[FarmRead]
    root_farms: list[FarmRead]
    event_count: int = Field(ge=0)
