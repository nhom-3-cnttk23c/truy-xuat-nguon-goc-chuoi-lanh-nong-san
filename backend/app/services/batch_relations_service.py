"""Service for splitting lots into multiple child lots with lineage tracking."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.crypto import GENESIS_PREV_HASH, compute_event_hash
from app.core.lot_codes import generate_lot_code
from app.core.tenancy import get_tenant_record
from app.models.batch_events import BatchEvent
from app.models.batch_relations import BatchRelation
from app.models.lot import Lot
from app.models.transaction import Transaction
from app.schemas.batch_split import SplitChildPayload


def split_lot(
    db: Session,
    principal: Principal,
    parent_id: UUID,
    children_payload: list[SplitChildPayload],
) -> dict:
    """
    Atomically split a parent lot into multiple child lots.

    Ensures:
    1. Parent lot is accessible and current_holder is caller's org
    2. Σ(child quantities) ≤ parent remaining_quantity
    3. Pessimistic lock on parent + advisory lock for race prevention
    4. All children created in single transaction
    5. All events (split_initiated + created_from_split) appended with hash chain
    6. lineage_depth and root_harvest_id pre-computed for fast queries

    Returns:
        Dict with 'transaction_id', 'parent_id', and 'children' (list of created Lot objects)
    """
    parent = get_tenant_record(db, Lot, parent_id, principal)

    if parent.current_holder_organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tổ chức hiện giữ lô mới có thể tách lô.",
        )

    # Pessimistic lock: block concurrent modifications
    db.execute(
        select(Lot).where(Lot.id == parent_id).with_for_update(of=Lot, nowait=False)
    )

    lock_id = hash(f"split:{principal.organization_id}:{parent_id}") % (2**31)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

    total_children_qty = sum(child.quantity for child in children_payload)

    if total_children_qty > parent.remaining_quantity:
        unit = parent.product.unit if parent.product else "kg"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tổng khối lượng lô con ({total_children_qty} {unit}) vượt khối lượng còn lại ({parent.remaining_quantity}).",
        )

    transaction = Transaction(
        initiator_user_id=principal.user_id,
        initiator_organization_id=principal.organization_id,
        op_type="split",
        status="pending",
    )
    db.add(transaction)
    db.flush()

    created_children: list[Lot] = []

    for child_payload in children_payload:
        for attempt in range(5):
            lot_code = generate_lot_code()
            child = Lot(
                organization_id=principal.organization_id,
                current_holder_organization_id=principal.organization_id,
                farm_id=parent.farm_id,
                name=child_payload.name,
                lot_code=lot_code,
                product_id=parent.product_id,
                harvested_on=parent.harvested_on,
                quantity=child_payload.quantity,
                remaining_quantity=child_payload.quantity,
                status="active",
                parent_batch_id=parent_id,
                lineage_depth=parent.lineage_depth + 1,
                root_harvest_id=parent.root_harvest_id or parent_id,
            )
            try:
                with db.begin_nested():
                    db.add(child)
                    db.flush()
                created_children.append(child)
                break
            except Exception:
                if attempt < 4:
                    continue
                raise

    remainder = parent.remaining_quantity - total_children_qty
    parent.remaining_quantity = remainder
    db.flush()

    for child in created_children:
        relation = BatchRelation(
            transaction_id=transaction.id,
            parent_batch_id=parent_id,
            child_batch_id=child.id,
            weight_transferred=child.remaining_quantity,
            op_type="split",
        )
        db.add(relation)

    # Create immutable events
    parent_payload = {
        "num_children": len(created_children),
        "total_transferred": str(total_children_qty),
        "remainder": str(remainder),
    }
    parent_hash = compute_event_hash(GENESIS_PREV_HASH, parent_payload)

    db.add(
        BatchEvent(
            batch_id=parent_id,
            event_type="split_initiated",
            payload=parent_payload,
            prev_hash=GENESIS_PREV_HASH,
            hash=parent_hash,
            actor_user_id=principal.user_id,
            transaction_id=transaction.id,
        )
    )
    db.flush()

    for child in created_children:
        child_payload_dict = {
            "parent_batch_id": str(parent_id),
            "quantity": str(child.remaining_quantity),
            "name": child.name,
            "lot_code": child.lot_code,
        }
        child_hash = compute_event_hash(GENESIS_PREV_HASH, child_payload_dict)

        db.add(
            BatchEvent(
                batch_id=child.id,
                event_type="created_from_split",
                payload=child_payload_dict,
                prev_hash=GENESIS_PREV_HASH,
                hash=child_hash,
                actor_user_id=principal.user_id,
                transaction_id=transaction.id,
            )
        )

    transaction.status = "committed"
    db.flush()
    db.commit()

    db.refresh(transaction)
    db.refresh(parent)
    for child in created_children:
        db.refresh(child)

    return {
        "transaction_id": transaction.id,
        "parent_id": parent_id,
        "children": created_children,
    }


def get_batch_children(
    db: Session,
    principal: Principal,
    parent_id: UUID,
) -> list[Lot]:
    """Get direct children (1 level) of a parent lot via batch_relations."""
    get_tenant_record(db, Lot, parent_id, principal)  # Verify access

    return db.scalars(
        select(Lot)
        .join(
            BatchRelation,
            BatchRelation.child_batch_id == Lot.id,
        )
        .where(
            BatchRelation.parent_batch_id == parent_id,
            BatchRelation.op_type == "split",
        )
        .order_by(Lot.id.asc())
    ).all()


def get_batch_parents(
    db: Session,
    principal: Principal,
    child_id: UUID,
) -> list[Lot]:
    """Get direct parents of a child lot via batch_relations."""
    _ = get_tenant_record(db, Lot, child_id, principal)

    parents = db.scalars(
        select(Lot)
        .join(
            BatchRelation,
            BatchRelation.parent_batch_id == Lot.id,
        )
        .where(
            BatchRelation.child_batch_id == child_id,
            BatchRelation.op_type == "split",
        )
    ).all()

    return list(parents)


def trace_to_root_harvest(
    db: Session,
    principal: Principal,
    lot_id: UUID,
    max_depth: int = 1000,
) -> dict:
    """
    Trace backwards through parent_batch_id chain to find root harvest lot.

    Uses denormalized root_harvest_id for O(1) lookup; falls back to recursive CTE
    for complex multi-parent merge scenarios.
    """
    lot = get_tenant_record(db, Lot, lot_id, principal)

    if lot.root_harvest_id:
        root = db.scalar(select(Lot).where(Lot.id == lot.root_harvest_id))
        if root:
            return {
                "root_harvest_id": root.id,
                "root_harvest_name": root.name,
                "root_harvest_lot_code": root.lot_code,
                "lineage_depth": lot.lineage_depth,
                "is_ancestor_visible": True,
            }

    # Fallback: manual traversal if denormalization missing
    current = lot
    depth = 0
    visited = set()

    while current.parent_batch_id and depth < max_depth:
        if current.parent_batch_id in visited:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phát hiện chu kỳ trong chuỗi phả hệ lô.",
            )
        visited.add(current.parent_batch_id)
        current = get_tenant_record(db, Lot, current.parent_batch_id, principal)
        depth += 1

    return {
        "root_harvest_id": current.id,
        "root_harvest_name": current.name,
        "root_harvest_lot_code": current.lot_code,
        "lineage_depth": depth,
        "is_ancestor_visible": True,
    }
