from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasPath, BaseModel, ConfigDict, Field, field_validator


class EventCreate(BaseModel):
    """Schema for appending a new immutable event to a lot's traceability chain."""

    lot_id: UUID
    event_type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def disallow_system_records(cls, value: str) -> str:
        if value.strip().lower() in {
            "harvest_recorded",
            "handover_pending",
            "handover_accepted",
            "handover_rejected",
            "lot_split",
            "lot_merged",
            "lot_derived",
            "lot_moved",
            "lot_consumed",
        }:
            raise ValueError(
                "Sự kiện này chỉ được tạo qua thao tác nghiệp vụ tương ứng."
            )
        return value


class EventRead(BaseModel):
    """Schema for reading an immutable event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lot_id: UUID
    sequence_number: int
    event_type: str
    recorded_at: datetime
    payload: dict[str, Any]
    payload_redacted: bool = False
    prev_hash: str
    event_hash: str
    organization_name: str = Field(validation_alias=AliasPath("organization", "name"))


class IntegrityIssue(BaseModel):
    sequence_number: int
    kind: str


class IntegrityRead(BaseModel):
    valid: bool
    checked_events: int
    first_invalid_sequence: int | None = None
    issues: list[IntegrityIssue] = Field(default_factory=list)


class IntegrityCheckRead(IntegrityRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lot_id: UUID
    checked_at: datetime


class EventHistoryRead(BaseModel):
    events: list[EventRead]
    integrity: IntegrityRead
    next_cursor: int | None = None
    total: int = Field(ge=0)


# ARCHITECTURAL INVARIANT (N3-21):
# There is deliberately NO `EventUpdate` schema.
# Events are strictly append-only and cannot be updated.
