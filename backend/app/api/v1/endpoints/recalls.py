from collections import defaultdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.models.event import Event
from app.models.lot import Lot


router = APIRouter()


@router.get("/lots")
@require_permission("lots:read")
def list_recall_lots(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    organization_id: UUID | None = Query(default=None),
) -> dict:
    query = select(Lot).order_by(Lot.name)

    # Người dùng thông thường chỉ xem các lô thuộc tổ chức của mình.
    if principal.role not in {"inspector", "system_admin"}:
        query = query.where(
            Lot.current_holder_organization_id == principal.organization_id
        )
    elif organization_id is not None:
        query = query.where(
            Lot.current_holder_organization_id == organization_id
        )

    lots = db.scalars(query).all()

    result_by_organization = defaultdict(list)

    for lot in lots:
        consumed_event = db.scalar(
            select(Event)
            .where(
                Event.lot_id == lot.id,
                Event.event_type == "lot_consumed",
            )
            .order_by(Event.sequence_number.desc())
        )

        if consumed_event is not None:
            consumed_quantity = lot.quantity or 0
        else:
            consumed_quantity = (lot.quantity or 0) - (
                lot.remaining_quantity or 0
            )

        remaining_quantity = lot.remaining_quantity or 0

        recoverable_quantity = remaining_quantity
        market_quantity = consumed_quantity

        organization = lot.current_holder_organization
        location = lot.current_location

        organization_name = (
            organization.name if organization is not None else None
        )

        location_name = location.name if location is not None else None

        item = {
            "lot_id": str(lot.id),
            "lot_code": lot.lot_code,
            "lot_name": lot.name,
            "organization_id": (
                str(lot.current_holder_organization_id)
                if lot.current_holder_organization_id
                else None
            ),
            "organization_name": organization_name,
            "location_id": (
                str(lot.current_location_id)
                if lot.current_location_id
                else None
            ),
            "location_name": location_name,
            "quantity": float(lot.quantity or 0),
            "remaining_quantity": float(remaining_quantity),
            "consumed_quantity": float(consumed_quantity),
            "recoverable_quantity": float(recoverable_quantity),
            "market_quantity": float(market_quantity),
            "status": lot.status,
        }

        result_by_organization[organization_name or "Chưa xác định"].append(
            item
        )

    organizations = []

    for organization_name, items in result_by_organization.items():
        organizations.append(
            {
                "organization_name": organization_name,
                "lots": items,
                "total_recoverable_quantity": sum(
                    item["recoverable_quantity"] for item in items
                ),
                "total_market_quantity": sum(
                    item["market_quantity"] for item in items
                )
            }
        )

    return {
        "total_lots": len(lots),
        "organizations": organizations,
    }