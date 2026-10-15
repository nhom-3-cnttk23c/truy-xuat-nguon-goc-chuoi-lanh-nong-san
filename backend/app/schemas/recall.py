"""Schemas for recall operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecallCreate(BaseModel):
    """Payload to open a recall order for a compromised lot."""

    lot_id: UUID
    reason: str = Field(..., min_length=20, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 20:
            raise ValueError("Lý do thu hồi là bắt buộc và phải có ít nhất 20 ký tự.")
        return trimmed


class RecallOrderRead(BaseModel):
    """Projection of an open or completed recall order."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recall_code: str
    root_lot_id: UUID
    opened_by_user_id: UUID
    opened_by_organization_id: UUID
    reason: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
