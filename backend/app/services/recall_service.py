"""Recall order management and shared blocking checks.

A lot is blocked from handover, split, and merge when:
- It belongs to a recall order with status='open', OR
- It belongs to a completed recall order AND still has incident_flag=True.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.lot import Lot
from app.models.recall import RecallOrder, RecallOrderLot
from app.schemas.recall import RecallOrderCreate
from app.services import event_service


def get_blocking_recall(
    db: Session, lot_id: UUID
) -> RecallOrder | None:
    """Return the recall order currently blocking this lot, or None.

    A lot is blocked when it is part of an open recall order, or part of a
    completed recall order whose lot entry still has an incident flag.
    """
    row = db.scalar(
        select(RecallOrder, RecallOrderLot)
        .join(RecallOrderLot, RecallOrderLot.recall_order_id == RecallOrder.id)
        .where(
            RecallOrderLot.lot_id == lot_id,
            (
                (RecallOrder.status == "open")
                | (
                    (RecallOrder.status == "completed")
                    & (RecallOrderLot.incident_flag.is_(True))
                )
            ),
        )
        .order_by(RecallOrder.created_at.desc())
    )
    if row is None:
        return None
    return row[0]


def raise_if_recall_blocked(db: Session, lot_id: UUID) -> None:
    """Raise 409 with the recall order code if the lot is blocked."""
    blocking = get_blocking_recall(db, lot_id)
    if blocking is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Lô đang bị thu hồi. Mã lệnh thu hồi: {blocking.code}. "
                "Vui lòng liên hệ quản trị viên."
            ),
        )


def create_recall_order(
    db: Session, principal: Principal, payload: RecallOrderCreate
) -> RecallOrder:
    existing = db.scalar(
        select(RecallOrder).where(RecallOrder.code == payload.code)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"Mã lệnh thu hồi {payload.code} đã tồn tại."
        )

    lots = list(
        db.scalars(
            select(Lot).where(
                Lot.id.in_(payload.lot_ids),
                Lot.current_holder_organization_id == principal.organization_id,
            )
        ).all()
    )
    if len(lots) != len(payload.lot_ids):
        raise HTTPException(
            403, "Một hoặc nhiều lô không thuộc tổ chức đang giữ."
        )

    order = RecallOrder(
        organization_id=principal.organization_id,
        code=payload.code,
        note=payload.note,
        created_by_user_id=principal.user_id,
    )
    db.add(order)
    db.flush()

    for lot in lots:
        db.add(
            RecallOrderLot(
                recall_order_id=order.id,
                organization_id=principal.organization_id,
                lot_id=lot.id,
                incident_flag=True,
            )
        )

    db.flush()
    for lot in lots:
        event_service.append_event(
            db,
            principal,
            lot.id,
            event_type="recall_issued",
            payload={
                "recall_order_id": str(order.id),
                "recall_code": order.code,
                "recall_status": "open",
                "note": payload.note,
            },
        )
    db.commit()
    db.refresh(order)
    return order


def list_recall_orders(
    db: Session, principal: Principal, *, status_filter: str | None = None
) -> list[RecallOrder]:
    stmt = (
        select(RecallOrder)
        .where(RecallOrder.organization_id == principal.organization_id)
        .order_by(RecallOrder.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(RecallOrder.status == status_filter)
    return list(db.scalars(stmt).all())


def complete_recall_order(
    db: Session, principal: Principal, recall_order_id: UUID
) -> RecallOrder:
    order = db.get(RecallOrder, recall_order_id)
    if order is None or order.organization_id != principal.organization_id:
        raise HTTPException(404, "Không tìm thấy lệnh thu hồi.")
    if order.status == "completed":
        raise HTTPException(409, "Lệnh thu hồi đã hoàn tất từ trước.")

    from datetime import UTC, datetime

    order.status = "completed"
    order.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return order


def update_incident_flag(
    db: Session,
    principal: Principal,
    recall_order_id: UUID,
    lot_id: UUID,
    incident_flag: bool,
) -> None:
    entry = db.scalar(
        select(RecallOrderLot).where(
            RecallOrderLot.recall_order_id == recall_order_id,
            RecallOrderLot.lot_id == lot_id,
        )
    )
    if entry is None:
        raise HTTPException(404, "Không tìm thấy lô trong lệnh thu hồi.")

    order = db.get(RecallOrder, recall_order_id)
    if order is None or order.organization_id != principal.organization_id:
        raise HTTPException(404, "Không tìm thấy lệnh thu hồi.")

    entry.incident_flag = incident_flag
    db.commit()
