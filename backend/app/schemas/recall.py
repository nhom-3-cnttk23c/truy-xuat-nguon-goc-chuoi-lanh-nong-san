from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

RecallOrderStatus = Literal["open", "completed"]


class RecallOrderCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    lot_ids: list[UUID] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Mã lệnh thu hồi phải là văn bản.")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Mã lệnh thu hồi không được để trống.")
        return normalized


class RecallOrderLotRead(BaseModel):
    id: UUID
    lot_id: UUID
    lot_code: str | None
    lot_name: str
    incident_flag: bool


class RecallOrderRead(BaseModel):
    id: UUID
    code: str
    status: RecallOrderStatus
    note: str | None
    created_at: datetime
    completed_at: datetime | None
    lots: list[RecallOrderLotRead]


class RecallOrderLotIncidentUpdate(BaseModel):
    incident_flag: bool
