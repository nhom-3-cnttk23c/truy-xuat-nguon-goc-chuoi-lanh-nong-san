from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.models.event import Event
from app.schemas.event import (
    EventCreate,
    EventHistoryRead,
    EventRead,
    IntegrityCheckRead,
    IntegrityRead,
)
from app.services import event_service

router = APIRouter()


@router.get("/lots/{lot_id}/history", response_model=EventHistoryRead)
@require_permission("events:read")
def get_lot_history(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=500)] = 500,
) -> dict:
    return event_service.get_event_history(
        db, principal, lot_id, after=after, page_size=page_size
    )


@router.get("/lots/{lot_id}/integrity", response_model=IntegrityRead)
@require_permission("events:verify")
def verify_lot_integrity(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return event_service.verify_lot_integrity(db, principal, lot_id)


@router.post(
    "/lots/{lot_id}/integrity-checks",
    response_model=IntegrityCheckRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission("events:verify")
def record_lot_integrity_check(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return event_service.record_integrity_check(db, principal, lot_id)


@router.get("/lots/{lot_id}/integrity-checks", response_model=list[IntegrityCheckRead])
@require_permission("events:verify")
def get_lot_integrity_check_history(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list:
    return event_service.get_integrity_check_history(db, principal, lot_id)


@router.get("/", response_model=list[EventRead])
@require_permission("events:read")
def list_events(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    lot_id: UUID | None = None,
) -> list[EventRead]:
    """List all events accessible to the caller's organization."""
    return event_service.list_events(db, principal, lot_id)


@router.post("/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
@require_permission("events:create")
def create_event(
    payload: EventCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Event:
    """Record a new immutable event into the lot's traceability chain.

    The event is cryptographically linked to the previous event via SHA-256 hash chaining.
    """
    return event_service.record_event(db, principal, payload)


@router.get("/{event_id}", response_model=EventRead)
@require_permission("events:read")
def get_event(
    event_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> EventRead:
    """Read a specific event by ID with tenant isolation."""
    return event_service.get_event_by_id(db, principal, event_id)


# ARCHITECTURAL INVARIANT (N3-21):
# Deliberately NO PUT, PATCH, or DELETE routes exist for events.
# Any HTTP PUT/PATCH/DELETE request will be rejected with 405 Method Not Allowed.
