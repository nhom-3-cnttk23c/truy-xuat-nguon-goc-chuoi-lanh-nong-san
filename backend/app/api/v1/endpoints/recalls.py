from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.models.lot import Lot
from app.models.recall import RecallOrder, RecallOrderLot
from app.schemas.recall import (
    RecallOrderCreate,
    RecallOrderLotRead,
    RecallOrderLotIncidentUpdate,
    RecallOrderRead,
)
from app.services import recall_service

router = APIRouter()


def _to_read(db: Session, order: RecallOrder) -> RecallOrderRead:
    rows = db.execute(
        select(RecallOrderLot, Lot)
        .join(Lot, Lot.id == RecallOrderLot.lot_id)
        .where(RecallOrderLot.recall_order_id == order.id)
        .order_by(Lot.lot_code)
    ).all()
    return RecallOrderRead(
        id=order.id,
        code=order.code,
        status=order.status,
        note=order.note,
        created_at=order.created_at,
        completed_at=order.completed_at,
        lots=[
            RecallOrderLotRead(
                id=entry.id,
                lot_id=entry.lot_id,
                lot_code=lot.lot_code,
                lot_name=lot.name,
                incident_flag=entry.incident_flag,
            )
            for entry, lot in rows
        ],
    )


@router.get("", response_model=list[RecallOrderRead])
@require_permission("recalls:manage")
def list_orders(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(pattern="^(open|completed)$")] = None,
) -> list[RecallOrderRead]:
    orders = recall_service.list_recall_orders(
        db, principal, status_filter=status_filter
    )
    return [_to_read(db, order) for order in orders]


@router.post("", response_model=RecallOrderRead, status_code=status.HTTP_201_CREATED)
@require_permission("recalls:manage")
def create_order(
    payload: RecallOrderCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RecallOrderRead:
    order = recall_service.create_recall_order(db, principal, payload)
    return _to_read(db, order)


@router.post("/{recall_order_id}/complete", response_model=RecallOrderRead)
@require_permission("recalls:manage")
def complete_order(
    recall_order_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RecallOrderRead:
    order = recall_service.complete_recall_order(db, principal, recall_order_id)
    return _to_read(db, order)


@router.patch("/{recall_order_id}/lots/{lot_id}", response_model=RecallOrderRead)
@require_permission("recalls:manage")
def update_lot_incident_flag(
    recall_order_id: UUID,
    lot_id: UUID,
    payload: RecallOrderLotIncidentUpdate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RecallOrderRead:
    recall_service.update_incident_flag(
        db, principal, recall_order_id, lot_id, payload.incident_flag
    )
    order = db.get(RecallOrder, recall_order_id)
    return _to_read(db, order)
