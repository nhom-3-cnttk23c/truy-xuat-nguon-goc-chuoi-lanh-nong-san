from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    """Schema for appending a new immutable event to a lot's traceability chain."""

    lot_id: UUID
    event_type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


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
    prev_hash: str
    event_hash: str


# ARCHITECTURAL INVARIANT (N3-21):
# There is deliberately NO `EventUpdate` schema.
# Events are strictly append-only and cannot be updated.
