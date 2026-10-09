from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SplitChildPayload(BaseModel):
    """Child lot specification in a split operation."""

    name: str = Field(..., min_length=1, max_length=200)
    quantity: Decimal = Field(..., gt=0, max_digits=14, decimal_places=3)


class LotSplitRequest(BaseModel):
    """Request to split a parent lot into multiple child lots."""

    children: list[SplitChildPayload] = Field(..., min_items=1, max_items=100)
    note: str | None = Field(None, max_length=500)


class LotSplitResponse(BaseModel):
    """Response after splitting a lot."""

    model_config = ConfigDict(from_attributes=True)

    transaction_id: UUID
    parent_id: UUID
    children: list["LotRead"]  # Forward ref to avoid circular import


class LotOriginTrace(BaseModel):
    """Response when tracing lot to root harvest."""

    model_config = ConfigDict(from_attributes=True)

    root_harvest_id: UUID
    root_harvest_name: str
    root_harvest_lot_code: str | None
    lineage_depth: int
    is_ancestor_visible: bool


class BatchRelationRead(BaseModel):
    """Read schema for a batch relation (DAG edge)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    parent_batch_id: UUID
    child_batch_id: UUID
    weight_transferred: Decimal
    op_type: str
    created_at: str


class BatchEventRead(BaseModel):
    """Read schema for a batch event (immutable lineage event)."""

    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    batch_id: UUID
    event_type: str
    payload: dict
    prev_hash: str
    hash: str
    actor_user_id: UUID
    transaction_id: UUID
    recorded_at: str


# Import at end to avoid circular reference
from app.schemas.lot import LotRead  # noqa: E402, F401
