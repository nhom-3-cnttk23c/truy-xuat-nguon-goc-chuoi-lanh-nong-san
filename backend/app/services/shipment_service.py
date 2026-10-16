"""Service layer for cold chain shipments and lot containment (N3-58)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.lot_codes import generate_lot_code
from app.models.lot import Lot
from app.models.shipment import Shipment, ShipmentLot
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDetailRead,
    ShipmentLotItemRead,
    ShipmentRead,
)
from app.services import event_service


def _generate_shipment_code(db: Session) -> str:
    """Generate a collision-resistant human-readable shipment code."""
    year = datetime.now(UTC).year
    for _ in range(5):
        candidate = f"SH-{year}-{generate_lot_code()[:6]}"
        exists = db.scalar(
            select(Shipment.id).where(Shipment.shipment_code == candidate)
        )
        if not exists:
            return candidate
    raise RuntimeError("Không thể tạo mã chuyến vận chuyển duy nhất, vui lòng thử lại.")


def _to_shipment_read(shipment: Shipment) -> ShipmentRead:
    """Transform Shipment model into summary projection."""
    return ShipmentRead(
        id=shipment.id,
        shipment_code=shipment.shipment_code,
        organization_id=shipment.organization_id,
        created_by_user_id=shipment.created_by_user_id,
        container_code=shipment.container_code,
        status=shipment.status,
        notes=shipment.notes,
        created_at=shipment.created_at,
        completed_at=shipment.completed_at,
        lot_count=len(shipment.shipment_lots),
    )


def _to_shipment_detail_read(shipment: Shipment) -> ShipmentDetailRead:
    """Transform Shipment model into detailed projection including lot items."""
    lot_items: list[ShipmentLotItemRead] = []
    for item in shipment.shipment_lots:
        lot = item.lot
        lot_items.append(
            ShipmentLotItemRead(
                lot_id=item.lot_id,
                lot_code=lot.lot_code if lot else None,
                name=lot.name if lot else None,
                quantity=str(lot.quantity) if lot else None,
                remaining_quantity=str(lot.remaining_quantity) if lot else None,
                status=lot.status if lot else None,
                loaded_at=item.loaded_at,
                unloaded_at=item.unloaded_at,
            )
        )

    return ShipmentDetailRead(
        id=shipment.id,
        shipment_code=shipment.shipment_code,
        organization_id=shipment.organization_id,
        created_by_user_id=shipment.created_by_user_id,
        container_code=shipment.container_code,
        status=shipment.status,
        notes=shipment.notes,
        created_at=shipment.created_at,
        completed_at=shipment.completed_at,
        lot_count=len(lot_items),
        lots=lot_items,
    )


def create_shipment(
    db: Session,
    principal: Principal,
    payload: ShipmentCreate,
) -> ShipmentDetailRead:
    """Declare and start a cold transport shipment with multiple lots and a refrigerated container.

    Acceptance criteria:
    - Chuyến có mã, thùng lạnh, danh sách lô do tổ chức tôi giữ, trạng thái đang chạy hoặc đã kết thúc;
    - Sự kiện lên xe và xuống xe ghi vào chuỗi mỗi lô.
    - NFR: một lô chỉ nằm trong một chuyến đang chạy tại một thời điểm.
    """
    if principal.role not in {
        "transporter",
        "cooperative",
        "distributor",
        "organization_admin",
        "system_admin",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vai trò của bạn không có quyền mở chuyến vận chuyển.",
        )

    validated_lots: list[Lot] = []
    for lot_id in payload.lot_ids:
        lot = db.get(Lot, lot_id)
        if lot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy lô hàng với ID {lot_id}.",
            )

        if lot.status == "consumed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Lô hàng {lot.lot_code or str(lot.id)} đã tiêu thụ hết, không thể đưa lên chuyến vận chuyển.",
            )

        if (
            principal.role != "system_admin"
            and lot.current_holder_organization_id != principal.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Lô hàng {lot.lot_code or str(lot.id)} không do tổ chức của bạn đang nắm giữ.",
            )

        # NFR Check: Một lô chỉ nằm trong một chuyến đang chạy tại một thời điểm
        active_shipment = db.scalar(
            select(Shipment)
            .join(ShipmentLot, ShipmentLot.shipment_id == Shipment.id)
            .where(
                ShipmentLot.lot_id == lot.id,
                ShipmentLot.unloaded_at.is_(None),
                Shipment.status == "in_transit",
            )
        )
        if active_shipment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "LOT_ALREADY_IN_TRANSIT",
                    "message": f"Lô {lot.lot_code or str(lot.id)} hiện đang nằm trong một chuyến vận chuyển khác ({active_shipment.shipment_code}).",
                    "lot_id": str(lot.id),
                    "lot_code": lot.lot_code,
                    "active_shipment_id": str(active_shipment.id),
                    "active_shipment_code": active_shipment.shipment_code,
                },
            )

        validated_lots.append(lot)

    shipment_code = (
        payload.shipment_code.strip()
        if payload.shipment_code
        else _generate_shipment_code(db)
    )

    shipment = Shipment(
        shipment_code=shipment_code,
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
        container_code=payload.container_code.strip(),
        notes=payload.notes.strip() if payload.notes else None,
        status="in_transit",
    )
    db.add(shipment)
    db.flush()

    # Link lots and record immutable shipment_loaded event in each lot's event history
    for lot in validated_lots:
        shipment_lot = ShipmentLot(
            shipment_id=shipment.id,
            lot_id=lot.id,
        )
        db.add(shipment_lot)

        event_service.append_event(
            db,
            principal,
            lot.id,
            event_type="shipment_loaded",
            payload={
                "shipment_id": str(shipment.id),
                "shipment_code": shipment.shipment_code,
                "container_code": shipment.container_code,
                "action": "loaded_on_vehicle",
                "notes": shipment.notes,
            },
        )

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể mở chuyến vận chuyển do xung đột trạng thái lô hàng hoặc mã chuyến.",
        ) from exc

    db.refresh(shipment)
    return _to_shipment_detail_read(shipment)


def complete_shipment(
    db: Session,
    principal: Principal,
    shipment_id: UUID,
) -> ShipmentDetailRead:
    """Complete a shipment and record shipment_unloaded events in each lot's history."""
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chuyến vận chuyển.",
        )

    if (
        principal.role not in {"inspector", "system_admin"}
        and shipment.organization_id != principal.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thao tác trên chuyến vận chuyển này.",
        )

    if shipment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chuyến vận chuyển này đã được kết thúc trước đó.",
        )

    now = datetime.now(UTC)
    shipment.status = "completed"
    shipment.completed_at = now

    for item in shipment.shipment_lots:
        item.unloaded_at = now
        event_service.append_event(
            db,
            principal,
            item.lot_id,
            event_type="shipment_unloaded",
            payload={
                "shipment_id": str(shipment.id),
                "shipment_code": shipment.shipment_code,
                "container_code": shipment.container_code,
                "action": "unloaded_from_vehicle",
            },
        )

    db.commit()
    db.refresh(shipment)
    return _to_shipment_detail_read(shipment)


def list_shipments(
    db: Session,
    principal: Principal,
    status_filter: str | None = None,
) -> list[ShipmentRead]:
    """List shipments visible to the principal."""
    stmt = select(Shipment).order_by(Shipment.created_at.desc())

    if principal.role not in {"inspector", "system_admin"}:
        stmt = stmt.where(Shipment.organization_id == principal.organization_id)

    if status_filter:
        stmt = stmt.where(Shipment.status == status_filter)

    shipments = list(db.scalars(stmt).all())
    return [_to_shipment_read(s) for s in shipments]


def get_shipment(
    db: Session,
    principal: Principal,
    shipment_id: UUID,
) -> ShipmentDetailRead:
    """Retrieve detailed information of a single shipment."""
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chuyến vận chuyển.",
        )

    if (
        principal.role not in {"inspector", "system_admin"}
        and shipment.organization_id != principal.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem chuyến vận chuyển này.",
        )

    return _to_shipment_detail_read(shipment)
