"""Atomic transformations; relation weights preserve immutable provenance."""

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.lot_codes import generate_lot_code
from app.models.lot import Lot
from app.models.lot_relation import LotRelation
from app.schemas.lineage import LotMerge, LotSplit
from app.services import event_service
from app.services.lot_lifecycle_service import validate_locations


def _lock_parents(
    db: Session, principal: Principal, ids: list[UUID]
) -> dict[UUID, Lot]:
    # Stable ordering prevents deadlocks between overlapping multi-parent merges.
    lots = list(
        db.scalars(
            select(Lot)
            .where(
                Lot.id.in_(ids),
                Lot.current_holder_organization_id == principal.organization_id,
            )
            .order_by(Lot.id)
            .with_for_update(of=Lot)
            .execution_options(populate_existing=True)
        ).all()
    )
    if len(lots) != len(ids):
        raise HTTPException(403, "Bạn chỉ được xử lý lô do tổ chức mình đang giữ.")
    for lot in lots:
        if lot.status != "active":
            raise HTTPException(
                409,
                f"Lô {lot.lot_code or lot.name} không thể xử lý: lô phải đang hoạt động và không chờ bàn giao.",
            )
        if lot.product_id is None:
            raise HTTPException(
                422,
                f"Lô {lot.lot_code or lot.name} chưa có nông sản để xác định đơn vị khối lượng.",
            )
    return {lot.id: lot for lot in lots}


def _allocate(lot: Lot, quantity: Decimal) -> None:
    if quantity > lot.remaining_quantity:
        raise HTTPException(
            409,
            f"Lô {lot.lot_code or lot.name} chỉ còn {lot.remaining_quantity:.3f} {lot.product.unit if lot.product else 'đơn vị'}. Khối lượng yêu cầu {quantity:.3f} vượt quá lượng còn lại.",
        )
    lot.remaining_quantity -= quantity
    if lot.remaining_quantity == 0:
        lot.status = "closed"


def _derived_lot(
    db: Session, principal: Principal, parent: Lot, name: str, quantity: Decimal
) -> Lot:
    if quantity > Decimal("99999999999.999"):
        raise HTTPException(422, "Tổng khối lượng vượt giới hạn lưu trữ.")
    for _ in range(5):
        lot = Lot(
            organization_id=principal.organization_id,
            current_holder_organization_id=principal.organization_id,
            farm_id=None,
            name=name,
            lot_code=generate_lot_code(),
            product_id=parent.product_id,
            quantity=quantity,
            remaining_quantity=quantity,
            status="active",
        )
        try:
            with db.begin_nested():
                db.add(lot)
                db.flush()
            return lot
        except IntegrityError as error:
            if (
                getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                != "uq_lots_lot_code"
            ):
                raise
    raise HTTPException(503, "Không thể cấp mã lô duy nhất. Vui lòng thử lại.")


def _edge(
    db: Session,
    principal: Principal,
    parent: Lot,
    child: Lot,
    quantity: Decimal,
    operation: str,
) -> None:
    db.add(
        LotRelation(
            organization_id=principal.organization_id,
            parent_lot_id=parent.id,
            child_lot_id=child.id,
            quantity=quantity,
            operation=operation,
        )
    )


def split_lot(
    db: Session, principal: Principal, lot_id: UUID, payload: LotSplit
) -> dict:
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('split:' || :parent_id))"),
                {"parent_id": str(lot_id)},
            )
        parent = _lock_parents(db, principal, [lot_id])[lot_id]
        validate_locations(
            db,
            principal,
            {item.location_id for item in payload.children if item.location_id},
        )
        _allocate(
            parent, sum((child.quantity for child in payload.children), Decimal("0"))
        )
        children = []
        for item in payload.children:
            child = _derived_lot(db, principal, parent, item.name, item.quantity)
            child.current_location_id = item.location_id
            _edge(db, principal, parent, child, item.quantity, "split")
            children.append(child)
        event_service.append_event(
            db,
            principal,
            parent.id,
            event_type="lot_split",
            payload={
                "children": [
                    {
                        "lot_id": str(child.id),
                        "lot_code": child.lot_code,
                        "quantity": format(child.quantity, "f"),
                        "location_id": str(child.current_location_id)
                        if child.current_location_id
                        else None,
                    }
                    for child in children
                ],
                "note": payload.note,
            },
        )
        for child in children:
            event_service.append_event(
                db,
                principal,
                child.id,
                event_type="lot_derived",
                payload={
                    "operation": "split",
                    "parents": [
                        {
                            "lot_id": str(parent.id),
                            "quantity": format(child.quantity, "f"),
                        }
                    ],
                    "note": payload.note,
                },
            )
        db.commit()
        db.refresh(parent)
        for child in children:
            db.refresh(child)
        return {"parent": parent, "children": children}
    except Exception:
        db.rollback()
        raise


def merge_lots(db: Session, principal: Principal, payload: LotMerge) -> Lot:
    try:
        parents = _lock_parents(
            db, principal, [item.lot_id for item in payload.parents]
        )
        first = parents[payload.parents[0].lot_id]
        for parent in parents.values():
            if parent.product_id != first.product_id:
                raise HTTPException(
                    422,
                    f"Lô {parent.lot_code or parent.name} khác nông sản với lô {first.lot_code or first.name}. Chỉ được gộp các lô cùng nông sản.",
                )
        for item in payload.parents:
            _allocate(parents[item.lot_id], item.quantity)
        quantity = sum((item.quantity for item in payload.parents), Decimal("0"))
        child = _derived_lot(db, principal, first, payload.name, quantity)
        for item in payload.parents:
            parent = parents[item.lot_id]
            _edge(db, principal, parent, child, item.quantity, "merge")
            event_service.append_event(
                db,
                principal,
                parent.id,
                event_type="lot_merged",
                payload={
                    "child_lot_id": str(child.id),
                    "child_lot_code": child.lot_code,
                    "quantity": format(item.quantity, "f"),
                    "note": payload.note,
                },
            )
        event_service.append_event(
            db,
            principal,
            child.id,
            event_type="lot_derived",
            payload={
                "operation": "merge",
                "parents": [
                    {"lot_id": str(item.lot_id), "quantity": format(item.quantity, "f")}
                    for item in payload.parents
                ],
                "note": payload.note,
            },
        )
        db.commit()
        db.refresh(child)
        return child
    except Exception:
        db.rollback()
        raise
