"""Service layer for managing product recalls (N3-49) and lineage recall reporting (N3-51)."""

from collections import defaultdict, deque
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, aliased, contains_eager

from app.core.auth import Principal
from app.core.lot_codes import generate_lot_code
from app.core.tenancy import get_tenant_record, lot_is_historical
from app.models.identity import Organization
from app.models.location import Location
from app.models.lot import Lot
from app.models.lot_relation import LotRelation
from app.models.product import Product
from app.models.recall_order import RecallOrder
from app.schemas.location import LocationRead
from app.schemas.recall import (
    RecallCreate,
    RecallLotItem,
    RecallReport,
    RecallSummary,
)
from app.services import event_service
from app.services.traversal_service import _roots_and_check_cycle

ZERO_QUANTITY = Decimal("0.000")


# --- N3-49: Recall Orders Management ---


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


# --- N3-51: Recall Lineage Reporting ---


def get_recall_report(db: Session, principal: Principal, lot_id: UUID) -> dict:
    """Traverse all descendant lots to generate a comprehensive recall report.

    Indicates for each lot in the lineage tree:
    - Where it is located (organization and facility/warehouse address)
    - How much remains in custody (recoverable inventory)
    - How much has been consumed / sold to the market
    - Whether cross-contamination from multi-source merges is present
    """
    db.execute(text("SET LOCAL jit = off"))
    get_tenant_record(db, Lot, lot_id, principal, allow_historical=True)

    # Recursive forward walk to find all descendants starting from lot_id
    statement = text("""WITH RECURSIVE visible_edges AS MATERIALIZED (
      SELECT * FROM lot_relations
    ), walk(id) AS (
      SELECT CAST(:lot_id AS uuid)
      UNION SELECT r.child_lot_id FROM visible_edges r JOIN walk w ON r.parent_lot_id = w.id
    ) SELECT * FROM visible_edges WHERE parent_lot_id IN (SELECT id FROM walk)
      AND child_lot_id IN (SELECT id FROM walk)
    """)

    edges = list(
        db.scalars(
            select(LotRelation).from_statement(statement), {"lot_id": lot_id}
        ).all()
    )

    ids = {lot_id}
    for edge in edges:
        ids.update((edge.parent_lot_id, edge.child_lot_id))

    _roots_and_check_cycle(db, ids, edges)

    # Materialize organizations visible to caller under RLS
    visible_organizations = (
        select(Organization).cte("recall_organizations").prefix_with("MATERIALIZED")
    )
    organization = aliased(Organization, visible_organizations)

    rows = db.execute(
        select(Lot, Product, Location, lot_is_historical(Lot, principal))
        .outerjoin(Product, Product.id == Lot.product_id)
        .outerjoin(Location, Location.id == Lot.current_location_id)
        .outerjoin(organization, Lot.current_holder_organization_id == organization.id)
        .options(contains_eager(Lot.current_holder_organization, alias=organization))
        .where(Lot.id.in_(ids))
        .order_by(Lot.id)
    ).all()

    if len(rows) != len(ids):
        raise HTTPException(
            403, "Không đủ quyền truy cập toàn bộ phả hệ thu hồi của lô."
        )

    # Build adjacency maps within the descendant subgraph
    parents: dict[UUID, list[UUID]] = defaultdict(list)
    children: dict[UUID, list[UUID]] = defaultdict(list)
    for edge in edges:
        parents[edge.child_lot_id].append(edge.parent_lot_id)
        children[edge.parent_lot_id].append(edge.child_lot_id)

    # Topological traversal from root_lot to compute tier and multi-source merge status
    tiers: dict[UUID, int] = {lot_id: 1}
    multi_source_merge: dict[UUID, bool] = {lot_id: len(parents[lot_id]) > 1}

    indegree = {node_id: len(parents[node_id]) for node_id in ids}
    queue: deque[UUID] = deque([lot_id])
    topo_order: list[UUID] = []

    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for child_id in children[current]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                queue.append(child_id)

    # Calculate tier and is_multi_source_merge in topological order
    for node_id in topo_order:
        if node_id == lot_id:
            continue
        node_parents = parents[node_id]
        if node_parents:
            tiers[node_id] = max(tiers.get(p, 1) for p in node_parents) + 1
            is_multi = len(node_parents) > 1 or any(
                multi_source_merge.get(p, False) for p in node_parents
            )
            multi_source_merge[node_id] = is_multi
        else:
            tiers[node_id] = 2
            multi_source_merge[node_id] = False

    lot_items: dict[UUID, RecallLotItem] = {}
    involved_org_names: set[str] = set()

    for lot, product, location, historical in rows:
        unit = product.unit if product else "kg"
        status = lot.status
        tier = tiers.get(lot.id, 1)
        is_multi = multi_source_merge.get(lot.id, False)

        if status == "consumed":
            rem_qty = ZERO_QUANTITY
            cons_qty = (
                Decimal(str(lot.quantity))
                if lot.quantity is not None
                else ZERO_QUANTITY
            )
            rec_qty = ZERO_QUANTITY
        elif status == "closed":
            rem_qty = ZERO_QUANTITY
            cons_qty = ZERO_QUANTITY
            rec_qty = ZERO_QUANTITY
        else:
            rem_qty = Decimal(str(lot.remaining_quantity))
            cons_qty = ZERO_QUANTITY
            rec_qty = rem_qty

        holder_org_name = (
            lot.current_holder_organization.name
            if lot.current_holder_organization
            else None
        )
        holder_org_type = (
            lot.current_holder_organization.type
            if lot.current_holder_organization
            else None
        )
        if holder_org_name:
            involved_org_names.add(holder_org_name)

        loc_read = LocationRead.model_validate(location) if location else None

        item = RecallLotItem(
            id=lot.id,
            lot_code=lot.lot_code,
            name=lot.name,
            tier=tier,
            status=status,
            is_multi_source_merge=is_multi,
            organization_id=lot.organization_id,
            current_holder_organization_id=lot.current_holder_organization_id,
            current_holder_organization_name=holder_org_name,
            holder_org_type=holder_org_type,
            current_location_id=lot.current_location_id,
            current_location=loc_read,
            quantity=Decimal(str(lot.quantity)) if lot.quantity is not None else None,
            remaining_quantity=rem_qty,
            consumed_quantity=cons_qty,
            recoverable_quantity=rec_qty,
            unit=unit,
            harvested_on=lot.harvested_on,
            historical_only=historical,
            parent_lot_ids=parents[lot.id],
        )

        if historical:
            item.remaining_quantity = ZERO_QUANTITY
            item.recoverable_quantity = ZERO_QUANTITY
            item.current_holder_organization_id = None
            item.current_holder_organization_name = None
            item.holder_org_type = None
            item.current_location_id = None
            item.current_location = None
            item.status = "transferred"

        lot_items[lot.id] = item

    root_item = lot_items[lot_id]
    descendants = [
        lot_items[nid] for nid in topo_order if nid != lot_id and nid in lot_items
    ]

    total_recoverable = sum(d.recoverable_quantity for d in descendants)
    if root_item.status == "active":
        total_recoverable += root_item.recoverable_quantity

    total_consumed = sum(d.consumed_quantity for d in descendants)
    if root_item.status == "consumed":
        total_consumed += root_item.consumed_quantity

    has_multi = any(d.is_multi_source_merge for d in descendants)
    has_consumed = any(d.status == "consumed" for d in descendants)

    summary = RecallSummary(
        root_lot_id=root_item.id,
        root_lot_code=root_item.lot_code,
        root_lot_name=root_item.name,
        initial_quantity=root_item.quantity,
        unit=root_item.unit,
        total_affected_lots=len(ids),
        total_descendants_count=len(descendants),
        total_recoverable_kg=total_recoverable,
        total_consumed_kg=total_consumed,
        involved_organizations_count=len(involved_org_names),
        involved_organizations=sorted(involved_org_names),
        has_multi_source_merge=has_multi,
        has_consumed_lot=has_consumed,
    )

    report = RecallReport(
        root_lot=root_item,
        summary=summary,
        descendants=descendants,
        affected_lots=[root_item, *descendants],
    )

    return report.model_dump()
