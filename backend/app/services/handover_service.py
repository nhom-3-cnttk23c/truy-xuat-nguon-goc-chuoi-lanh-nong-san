from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.auth import Principal
from app.core.config import settings
from app.models.handover import Handover
from app.models.identity import Organization
from app.models.lot import Lot
from app.schemas.handover import HandoverCreate
from app.services import event_service, recall_service

PARTICIPANT_ORGANIZATION_TYPES = {"farm", "cooperative", "transport", "distribution"}


def list_transfer_organizations(
    db: Session, principal: Principal
) -> list[Organization]:
    return list(
        db.scalars(
            select(Organization)
            .where(
                Organization.id != principal.organization_id,
                Organization.is_active.is_(True),
                Organization.organization_type.in_(PARTICIPANT_ORGANIZATION_TYPES),
            )
            .order_by(Organization.name)
        ).all()
    )


def list_handovers(db: Session, principal: Principal, *, incoming: bool) -> list[dict]:
    sender = aliased(Organization)
    recipient = aliased(Organization)
    party_column = (
        Handover.to_organization_id if incoming else Handover.from_organization_id
    )
    rows = db.execute(
        select(Handover, Lot, sender.name, recipient.name)
        .join(Lot, Lot.id == Handover.lot_id)
        .join(sender, sender.id == Handover.from_organization_id)
        .join(recipient, recipient.id == Handover.to_organization_id)
        .where(party_column == principal.organization_id)
        .order_by(Handover.created_at.asc(), Handover.id.asc())
    ).all()
    return [
        {
            "id": handover.id,
            "lot_id": lot.id,
            "lot_code": lot.lot_code,
            "lot_name": lot.name,
            "from_organization_id": handover.from_organization_id,
            "from_organization_name": sender_name,
            "to_organization_id": handover.to_organization_id,
            "to_organization_name": recipient_name,
            "status": handover.status,
            "note": handover.note,
            "rejection_reason": handover.rejection_reason,
            "created_at": handover.created_at,
            "overdue_at": handover.overdue_at,
        }
        for handover, lot, sender_name, recipient_name in rows
    ]


def create_handover(db: Session, principal: Principal, payload: HandoverCreate) -> dict:
    if payload.to_organization_id == principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể bàn giao cho chính tổ chức của bạn.",
        )

    recipient = db.scalar(
        select(Organization).where(
            Organization.id == payload.to_organization_id,
            Organization.is_active.is_(True),
            Organization.organization_type.in_(PARTICIPANT_ORGANIZATION_TYPES),
        )
    )
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tổ chức nhận đang hoạt động.",
        )

    lot = db.scalar(
        select(Lot)
        .where(
            Lot.id == payload.lot_id,
            Lot.current_holder_organization_id == principal.organization_id,
        )
        .with_for_update(of=Lot)
    )
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền bàn giao lô này.",
        )
    if lot.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lô không ở trạng thái có thể bàn giao.",
        )
    recall_service.raise_if_recall_blocked(db, lot.id)

    handover = Handover(
        lot_id=lot.id,
        from_organization_id=principal.organization_id,
        to_organization_id=recipient.id,
        created_by_user_id=principal.user_id,
        note=payload.note,
    )
    db.add(handover)
    lot.status = "pending_handover"

    try:
        db.flush()
        event_service.append_event(
            db,
            principal,
            lot.id,
            event_type="handover_pending",
            payload={
                "handover_id": str(handover.id),
                "from_organization_id": str(principal.organization_id),
                "to_organization_id": str(recipient.id),
                "to_organization_name": recipient.name,
                "note": payload.note,
            },
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        diagnostic = getattr(error.orig, "diag", None)
        if (
            getattr(diagnostic, "constraint_name", None)
            == "uq_handovers_one_pending_per_lot"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lô đang có một bàn giao chờ xác nhận.",
            ) from error
        raise
    except Exception:
        db.rollback()
        raise

    db.refresh(handover)
    sender_name = db.scalar(
        select(Organization.name).where(Organization.id == principal.organization_id)
    )
    return {
        "id": handover.id,
        "lot_id": lot.id,
        "lot_code": lot.lot_code,
        "lot_name": lot.name,
        "from_organization_id": principal.organization_id,
        "from_organization_name": sender_name or "",
        "to_organization_id": recipient.id,
        "to_organization_name": recipient.name,
        "status": handover.status,
        "note": handover.note,
        "rejection_reason": handover.rejection_reason,
        "created_at": handover.created_at,
        "overdue_at": handover.overdue_at,
    }


def _get_incoming_pending(
    db: Session, principal: Principal, handover_id: UUID
) -> tuple[Handover, Lot]:
    handover = db.scalar(select(Handover).where(Handover.id == handover_id))
    if handover is None or handover.to_organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xử lý yêu cầu bàn giao này.",
        )
    if handover.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Yêu cầu bàn giao đã được xử lý.",
        )

    lot = db.scalar(
        select(Lot)
        .where(Lot.id == handover.lot_id)
        .with_for_update(of=Lot)
        .execution_options(populate_existing=True)
    )
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể tìm thấy lô đang chờ bàn giao.",
        )
    # The row lock may have waited for another accept/reject transaction. Refresh
    # the handover after acquiring it; the earlier identity-map value is stale.
    handover = db.scalar(
        select(Handover)
        .where(Handover.id == handover_id)
        .execution_options(populate_existing=True)
    )
    if handover is None or handover.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Yêu cầu bàn giao đã được xử lý.",
        )
    return handover, lot


def accept_handover(db: Session, principal: Principal, handover_id: UUID) -> Handover:
    handover, lot = _get_incoming_pending(db, principal, handover_id)
    if lot.current_holder_organization_id != handover.from_organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tổ chức đang giữ lô đã thay đổi.",
        )

    try:
        accepted_at = datetime.now(UTC)
        is_late = handover.overdue_at is not None or (
            handover.created_at
            < accepted_at - timedelta(hours=settings.HANDOVER_OVERDUE_HOURS)
        )
        overdue_at = handover.overdue_at or (accepted_at if is_late else None)
        accepted_event = event_service.append_event(
            db,
            principal,
            lot.id,
            event_type="handover_accepted",
            payload={
                "handover_id": str(handover.id),
                "from_organization_id": str(handover.from_organization_id),
                "to_organization_id": str(principal.organization_id),
                "late_acknowledgement": is_late,
                "overdue_at": overdue_at.isoformat() if overdue_at else None,
                "overdue_threshold_hours": settings.HANDOVER_OVERDUE_HOURS,
            },
        )
        lot.current_holder_organization_id = principal.organization_id
        lot.current_location_id = None
        lot.status = "active"
        # Keep the handover pending until the recipient's new custody is visible.
        db.flush()
        handover.status = "accepted"
        handover.resolved_by_user_id = principal.user_id
        # Historical RLS includes the acceptance event at the cutoff itself.
        handover.resolved_at = accepted_event.recorded_at
        handover.overdue_at = overdue_at
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(handover)
    return handover


def reject_handover(
    db: Session, principal: Principal, handover_id: UUID, reason: str
) -> Handover:
    handover, lot = _get_incoming_pending(db, principal, handover_id)
    if lot.current_holder_organization_id != handover.from_organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tổ chức đang giữ lô đã thay đổi.",
        )

    try:
        event_service.append_event(
            db,
            principal,
            lot.id,
            event_type="handover_rejected",
            payload={
                "handover_id": str(handover.id),
                "from_organization_id": str(handover.from_organization_id),
                "to_organization_id": str(principal.organization_id),
                "reason": reason,
            },
        )
        lot.status = "active"
        # The recipient may update the lot only while the handover is pending.
        db.flush()
        handover.status = "rejected"
        handover.rejection_reason = reason
        handover.resolved_by_user_id = principal.user_id
        handover.resolved_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(handover)
    return handover
