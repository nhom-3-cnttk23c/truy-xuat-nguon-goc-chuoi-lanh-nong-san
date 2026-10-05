from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.core.tenancy import get_tenant_record, tenant_select
from app.models.event import Event
from app.schemas.event import EventCreate, EventRead
from app.services import event_service

router = APIRouter()


@router.get("/", response_model=list[EventRead])
@require_permission("events:read")
def list_events(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Event]:
    """List all events accessible to the caller's organization."""
    return list(db.scalars(tenant_select(Event, principal)).all())


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
) -> Event:
    """Read a specific event by ID with tenant isolation."""
    return get_tenant_record(db, Event, event_id, principal)


# ARCHITECTURAL INVARIANT (N3-21):
# Deliberately NO PUT, PATCH, or DELETE routes exist for events.
# Any HTTP PUT/PATCH/DELETE request will be rejected with 405 Method Not Allowed.
