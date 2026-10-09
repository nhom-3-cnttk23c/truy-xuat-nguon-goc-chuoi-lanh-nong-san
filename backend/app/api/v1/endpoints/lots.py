from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.core.tenancy import get_tenant_record
from app.models.lot import Lot
from app.schemas.batch_split import (
    LotSplitRequest,
    LotSplitResponse,
    LotOriginTrace,
    BatchEventRead,
    BatchRelationRead,
)
from app.schemas.lot import LotCreate, LotListRead, LotRead
from app.services import batch_relations_service, lot_service

router = APIRouter()


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


@router.get("/{lot_id}", response_model=LotRead)
@require_permission("lots:read")
def get_lot(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Lot:
    return get_tenant_record(db, Lot, lot_id, principal)


@router.post("/{lot_id}/split", response_model=LotSplitResponse, status_code=status.HTTP_200_OK)
@require_permission("lots:create")
def split_lot(
    lot_id: UUID,
    payload: LotSplitRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> LotSplitResponse:
    """Split a lot into multiple child lots with full lineage tracking."""
    result = batch_relations_service.split_lot(
        db, principal, lot_id, payload.children
    )
    return LotSplitResponse(
        transaction_id=result["transaction_id"],
        parent_id=result["parent_id"],
        children=result["children"],
    )


@router.get("/{lot_id}/children", response_model=list[LotRead])
@require_permission("lots:read")
def get_lot_children(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Lot]:
    """Get direct child lots created from splitting this parent."""
    return batch_relations_service.get_batch_children(db, principal, lot_id)


@router.get("/{lot_id}/parents", response_model=list[LotRead])
@require_permission("lots:read")
def get_lot_parents(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Lot]:
    """Get direct parent lots from which this lot was split."""
    return batch_relations_service.get_batch_parents(db, principal, lot_id)


@router.get("/{lot_id}/lineage/origin", response_model=LotOriginTrace)
@require_permission("lots:read")
def trace_lot_origin(
    lot_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> LotOriginTrace:
    """Trace lot backwards to root harvest lot."""
    result = batch_relations_service.trace_to_root_harvest(db, principal, lot_id)
    return LotOriginTrace(
        root_harvest_id=result["root_harvest_id"],
        root_harvest_name=result["root_harvest_name"],
        root_harvest_lot_code=result["root_harvest_lot_code"],
        lineage_depth=result["lineage_depth"],
        is_ancestor_visible=result["is_ancestor_visible"],
    )
