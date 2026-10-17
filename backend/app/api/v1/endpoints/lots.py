from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.models.lot import Lot
from app.schemas.lineage import (
    LineageRead,
    LotDetailRead,
    LotMerge,
    LotSplit,
    SplitRead,
)
from app.schemas.location import LotConsume, LotMove
from app.schemas.lot import LotCreate, LotListRead, LotRead
from app.schemas.recall import RecallReport
from app.services import (
    lineage_service,
    lot_lifecycle_service,
    lot_service,
    recall_service,
    traversal_service,
)

router = APIRouter()


@router.post("/{lot_id}/move", response_model=LotRead)
@require_permission("locations:manage")
def move_lot(
    lot_id: UUID,
    payload: LotMove,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
):
    return lot_lifecycle_service.move_lot(db, principal, lot_id, payload)


@router.post("/{lot_id}/consume", response_model=LotRead)
@require_permission("lots:consume")
def consume_lot(
    lot_id: UUID,
    payload: LotConsume,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
):
    return lot_lifecycle_service.consume_lot(db, principal, lot_id, payload)


@router.post("/", response_model=LotRead, status_code=status.HTTP_201_CREATED)
@require_permission("lots:create")
def create_lot(
    payload: LotCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Lot:
    return lot_service.create_harvest_lot(db, principal, payload)


@router.get("/", response_model=LotListRead)
@require_permission("lots:read")
def list_lots(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    product_id: UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return lot_service.list_lots(
        db,
        principal,
        query=q,
        product_id=product_id,
        cursor=cursor,
        page_size=page_size,
    )


@router.post("/merge", response_model=LotRead, status_code=status.HTTP_201_CREATED)
@require_permission("lots:transform")
def merge_lots(
    payload: LotMerge,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Lot:
    return lineage_service.merge_lots(db, principal, payload)


@router.post(
    "/{lot_id}/split", response_model=SplitRead, status_code=status.HTTP_201_CREATED
)
@require_permission("lots:transform")
def split_lot(
    lot_id: UUID,
    payload: LotSplit,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return lineage_service.split_lot(db, principal, lot_id, payload)


@router.get("/{lot_id}/lineage", response_model=LineageRead)
@require_permission("lots:read")
def get_lineage(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    direction: Literal["ancestors", "descendants"] = "ancestors",
) -> dict:
    return traversal_service.get_lineage(db, principal, lot_id, direction)


@router.get("/{lot_id}", response_model=LotDetailRead)
@require_permission("lots:read")
def get_lot(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return traversal_service.get_detail(db, principal, lot_id)


@router.get("/{lot_id}/recall", response_model=RecallReport)
@require_permission("lots:read")
def get_lot_recall(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return recall_service.get_recall_report(db, principal, lot_id)
