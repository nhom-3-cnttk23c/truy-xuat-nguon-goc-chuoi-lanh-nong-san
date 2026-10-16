"""API endpoints for managing cold chain shipments (N3-58)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDetailRead,
    ShipmentRead,
)
from app.services import shipment_service

router = APIRouter()


@router.post(
    "",
    response_model=ShipmentDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Mở chuyến vận chuyển lạnh gắn nhiều lô và một thùng lạnh",
)
@router.post(
    "/",
    response_model=ShipmentDetailRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@require_permission("shipments:create")
def create_shipment_order(
    payload: ShipmentCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentDetailRead:
    return shipment_service.create_shipment(db, principal, payload)


@router.get(
    "",
    response_model=list[ShipmentRead],
    summary="Danh sách các chuyến vận chuyển",
)
@router.get(
    "/",
    response_model=list[ShipmentRead],
    include_in_schema=False,
)
@require_permission("shipments:read")
def list_shipment_orders(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[
        Literal["in_transit", "completed"] | None,
        Query(description="Lọc theo trạng thái chuyến"),
    ] = None,
) -> list[ShipmentRead]:
    return shipment_service.list_shipments(db, principal, status_filter=status)


@router.get(
    "/{shipment_id}",
    response_model=ShipmentDetailRead,
    summary="Chi tiết chuyến vận chuyển và danh sách lô hàng",
)
@require_permission("shipments:read")
def get_shipment_order(
    shipment_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentDetailRead:
    return shipment_service.get_shipment(db, principal, shipment_id)


@router.post(
    "/{shipment_id}/complete",
    response_model=ShipmentDetailRead,
    summary="Kết thúc chuyến vận chuyển và ghi sự kiện xuống xe",
)
@require_permission("shipments:complete")
def complete_shipment_order(
    shipment_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentDetailRead:
    return shipment_service.complete_shipment(db, principal, shipment_id)
