"""Service layer for managing product recalls."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.lot_codes import generate_lot_code
from app.models.lot import Lot
from app.models.recall_order import RecallOrder
from app.schemas.recall import RecallCreate
from app.services import event_service


def _generate_recall_code(db: Session) -> str:
    """Generate a collision-resistant human-readable recall code."""
    year = datetime.now(UTC).year
    for _ in range(5):
        candidate = f"RC-{year}-{generate_lot_code()[:6]}"
        exists = db.scalar(
            select(RecallOrder.id).where(RecallOrder.recall_code == candidate)
        )
        if not exists:
            return candidate
    raise RuntimeError("Không thể tạo mã thu hồi duy nhất, vui lòng thử lại.")


def open_recall(
    db: Session,
    principal: Principal,
    payload: RecallCreate,
) -> RecallOrder:
    """Open a new recall order for a compromised lot.

    - AC1: Inspector or holder org-admin opens recall with reason (min 20 chars),
           generates unique code, appends immutable event to lot.
    - AC2: Other roles get 403 Forbidden.
    - AC3: If lot already has an open recall, block with 409 and point to open recall.
    """
    if principal.role not in {"inspector", "system_admin", "organization_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ cán bộ kiểm tra hoặc quản trị tổ chức đang giữ lô được mở lệnh thu hồi.",
        )

    # Fetch lot using standard select (inspector has global read, org admin has tenant read)
    lot = db.get(Lot, payload.lot_id)
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lô hàng yêu cầu thu hồi.",
        )

    # Organization admin can only recall lots currently held by their organization
    if principal.role == "organization_admin":
        if lot.current_holder_organization_id != principal.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Quản trị viên chỉ được mở lệnh thu hồi cho lô do tổ chức mình đang giữ.",
            )

    # Terminal lots cannot receive events
    if lot.status == "consumed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể mở lệnh thu hồi trực tiếp trên lô đã tiêu thụ hết.",
        )

    # AC3: Check if lot already has an open recall order
    existing_open = db.scalar(
        select(RecallOrder).where(
            RecallOrder.root_lot_id == lot.id,
            RecallOrder.status == "open",
        )
    )
    if existing_open is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "RECALL_ALREADY_OPEN",
                "message": f"Lô này đã có lệnh thu hồi đang mở ({existing_open.recall_code}).",
                "recall_id": str(existing_open.id),
                "recall_code": existing_open.recall_code,
            },
        )

    recall_code = _generate_recall_code(db)
    order = RecallOrder(
        recall_code=recall_code,
        root_lot_id=lot.id,
        opened_by_user_id=principal.user_id,
        opened_by_organization_id=principal.organization_id,
        reason=payload.reason,
        status="open",
    )
    db.add(order)
    db.flush()

    # AC1: Record immutable recall_opened event in the lot's event history
    event_service.append_event(
        db,
        principal,
        lot.id,
        event_type="recall_opened",
        payload={
            "recall_id": str(order.id),
            "recall_code": order.recall_code,
            "reason": order.reason,
            "opened_by_role": principal.role,
            "opened_by_organization_id": str(principal.organization_id),
        },
    )

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        # In case of concurrent open recall, unique index blocks duplicate
        conflict = db.scalar(
            select(RecallOrder).where(
                RecallOrder.root_lot_id == lot.id,
                RecallOrder.status == "open",
            )
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "RECALL_ALREADY_OPEN",
                    "message": f"Lô này đã có lệnh thu hồi đang mở ({conflict.recall_code}).",
                    "recall_id": str(conflict.id),
                    "recall_code": conflict.recall_code,
                },
            ) from exc
        raise

    db.refresh(order)
    return order


def list_recalls(db: Session, principal: Principal) -> list[RecallOrder]:
    """List recall orders visible to the principal."""
    stmt = select(RecallOrder).order_by(RecallOrder.created_at.desc())

    if principal.role not in {"inspector", "system_admin"}:
        stmt = stmt.join(RecallOrder.root_lot).where(
            (RecallOrder.opened_by_organization_id == principal.organization_id)
            | (Lot.current_holder_organization_id == principal.organization_id)
        )

    return list(db.scalars(stmt).all())


def get_recall(db: Session, principal: Principal, recall_id: UUID) -> RecallOrder:
    """Get details of a single recall order."""
    order = db.get(RecallOrder, recall_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lệnh thu hồi.",
        )

    if principal.role not in {"inspector", "system_admin"}:
        is_opener = order.opened_by_organization_id == principal.organization_id
        is_holder = bool(
            order.root_lot
            and order.root_lot.current_holder_organization_id
            == principal.organization_id
        )
        if not (is_opener or is_holder):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền xem lệnh thu hồi này.",
            )

    return order
