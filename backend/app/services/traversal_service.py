"""Traverse each edge once; union CTEs terminate even for corrupted graphs."""

from collections import deque
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased, contains_eager

from app.core.auth import Principal
from app.core.tenancy import get_tenant_record, lot_is_historical
from app.models.event import Event
from app.models.farm import Farm
from app.models.identity import Organization
from app.models.lot import Lot
from app.models.lot_relation import LotRelation
from app.schemas.lot import LotRead
from app.services import ancestor_cache


def _roots_and_check_cycle(
    db: Session, ids: set[UUID], edges: list[LotRelation]
) -> list[UUID]:
    indegree = dict.fromkeys(ids, 0)
    children: dict[UUID, list[UUID]] = {id: [] for id in ids}
    for edge in edges:
        indegree[edge.child_lot_id] += 1
        children[edge.parent_lot_id].append(edge.child_lot_id)
    roots = [id for id, degree in indegree.items() if degree == 0]
    queue = deque(roots)
    visited = 0
    while queue:
        parent = queue.popleft()
        visited += 1
        for child in children[parent]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(ids):
        # Kahn's remainder also includes descendants of a cycle. Follow incoming
        # edges until a node repeats, so the notice names a node in the cycle.
        remaining = {id for id, degree in indegree.items() if degree > 0}
        parents: dict[UUID, list[UUID]] = {id: [] for id in remaining}
        for edge in edges:
            if edge.parent_lot_id in remaining and edge.child_lot_id in remaining:
                parents[edge.child_lot_id].append(edge.parent_lot_id)
        cycle_id = min(remaining)
        seen: set[UUID] = set()
        while cycle_id not in seen:
            seen.add(cycle_id)
            cycle_id = min(parents[cycle_id])
        # Read through the same RLS session; never disclose an unauthorized name.
        lot = db.get(Lot, cycle_id)
        label = (lot.lot_code or lot.name) if lot else str(cycle_id)
        raise HTTPException(
            409,
            f"Phát hiện chu trình trong dữ liệu phả hệ liên quan lô {label}; cần kiểm tra dữ liệu nguồn.",
        )
    return sorted(roots)


def get_lineage(
    db: Session, principal: Principal, lot_id: UUID, direction: str
) -> dict:
    get_tenant_record(db, Lot, lot_id, principal, allow_historical=True)
    ancestors = direction in {"ancestors", "detail"}
    next_column = "parent_lot_id" if ancestors else "child_lot_id"
    join_column = "child_lot_id" if ancestors else "parent_lot_id"
    # Column names are chosen above; all external values are bound parameters.
    condition = " OR parent_lot_id = :lot_id" if direction == "detail" else ""
    statement = text(f"""WITH RECURSIVE walk(id) AS (
      SELECT CAST(:lot_id AS uuid)
      UNION SELECT r.{next_column} FROM lot_relations r JOIN walk w ON r.{join_column} = w.id
    ) SELECT * FROM lot_relations WHERE parent_lot_id IN (SELECT id FROM walk)
      AND child_lot_id IN (SELECT id FROM walk){condition}
    """)
    cache_key = (
        str(db.get_bind().url),
        principal.user_id,
        principal.organization_id,
        principal.role,
        lot_id,
    )
    cached_ids = ancestor_cache.get(cache_key) if direction == "ancestors" else None
    edges = None
    if cached_ids is not None:
        # Re-read edges through RLS and detect new incoming relations. Only the
        # recursive discovery is skipped; grants and live fields remain fresh.
        candidate_edges = list(
            db.scalars(
                select(LotRelation).where(LotRelation.child_lot_id.in_(cached_ids))
            )
        )
        candidate_ids = {lot_id}
        for edge in candidate_edges:
            candidate_ids.update((edge.parent_lot_id, edge.child_lot_id))
        if candidate_ids == cached_ids:
            edges = candidate_edges
    if edges is None:
        edges = list(
            db.scalars(
                select(LotRelation).from_statement(statement), {"lot_id": lot_id}
            ).all()
        )
    ids = {lot_id}
    for edge in edges:
        ids.update((edge.parent_lot_id, edge.child_lot_id))
    roots = _roots_and_check_cycle(db, ids, edges)
    # Evaluate organization RLS once, rather than once per node when the
    # planner chooses a nested-loop join. The CTE uses the caller's RLS context.
    visible_organizations = (
        select(Organization).cte("lineage_organizations").prefix_with("MATERIALIZED")
    )
    organization = aliased(Organization, visible_organizations)
    rows = db.execute(
        select(Lot, Farm, lot_is_historical(Lot, principal))
        .outerjoin(Farm, Farm.id == Lot.farm_id)
        .outerjoin(organization, Lot.current_holder_organization_id == organization.id)
        .options(contains_eager(Lot.current_holder_organization, alias=organization))
        .where(Lot.id.in_(ids))
        .order_by(Lot.id)
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(403, "Không đủ quyền truy cập toàn bộ phả hệ của lô.")
    if direction == "ancestors":
        # Do not extend an existing entry indefinitely on cache hits.
        if cached_ids != ids:
            ancestor_cache.put(cache_key, ids)
    farms = {
        farm.id: farm for lot, farm, _ in rows if lot.id in roots and farm is not None
    }
    nodes = []
    for lot, _, historical in rows:
        node = LotRead.model_validate(lot).model_dump()
        node["historical_only"] = historical
        if historical:
            node.update(
                remaining_quantity=None,
                current_holder_organization_id=None,
                current_holder_organization_name=None,
                current_location_id=None,
                current_location=None,
                status="transferred",
            )
        nodes.append(node)
    return {
        "selected_lot_id": lot_id,
        "direction": direction,
        "nodes": nodes,
        "edges": edges,
        "roots": roots,
        "root_farms": list(farms.values()),
    }


def get_detail(db: Session, principal: Principal, lot_id: UUID) -> dict:
    """Read the selected lot and immediate relations; deep trace is a separate API."""
    get_tenant_record(db, Lot, lot_id, principal)
    edges = list(
        db.scalars(
            select(LotRelation).where(
                (LotRelation.parent_lot_id == lot_id)
                | (LotRelation.child_lot_id == lot_id)
            )
        )
    )
    ids = {lot_id}
    for edge in edges:
        ids.update((edge.parent_lot_id, edge.child_lot_id))
    _roots_and_check_cycle(db, ids, edges)
    event_count = (
        select(func.count())
        .select_from(Event)
        .where(Event.lot_id == lot_id)
        .scalar_subquery()
    )
    sources = (
        select(Lot.id, Lot.farm_id)
        .where(Lot.id == lot_id)
        .cte("detail_sources", recursive=True)
    )
    sources = sources.union(
        select(Lot.id, Lot.farm_id)
        .join(LotRelation, LotRelation.parent_lot_id == Lot.id)
        .join(sources, sources.c.id == LotRelation.child_lot_id)
    )
    root_farms = (
        select(func.jsonb_agg(func.to_jsonb(Farm.__table__.table_valued())))
        .select_from(Farm)
        .where(Farm.id.in_(select(sources.c.farm_id)))
        .scalar_subquery()
    )
    rows = db.execute(
        select(Lot, Farm, lot_is_historical(Lot, principal), event_count, root_farms)
        .outerjoin(Farm, Farm.id == Lot.farm_id)
        .where(Lot.id.in_(ids))
        .order_by(Lot.id)
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(403, "Không đủ quyền truy cập các lô liên quan trực tiếp.")
    nodes = {}
    farms = {}
    count = 0
    origins = []
    for lot, farm, historical, visible_event_count, origin_farms in rows:
        node = LotRead.model_validate(lot).model_dump()
        node["historical_only"] = historical
        if historical:
            node.update(
                remaining_quantity=None,
                current_holder_organization_id=None,
                current_holder_organization_name=None,
                current_location_id=None,
                current_location=None,
                status="transferred",
            )
        nodes[lot.id] = node
        if farm is not None:
            farms[farm.id] = farm
        if lot.id == lot_id:
            count = visible_event_count
            origins = origin_farms or []
    return {
        **LotRead.model_validate(nodes[lot_id]).model_dump(),
        "parents": [
            nodes[edge.parent_lot_id] for edge in edges if edge.child_lot_id == lot_id
        ],
        "children": [
            nodes[edge.child_lot_id] for edge in edges if edge.parent_lot_id == lot_id
        ],
        "direct_farms": list(farms.values()),
        "root_farms": origins,
        "event_count": count,
    }
