"""Tests for N3-39: Lot split with lineage tracking and immutable batch events."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.main import app
from app.models.batch_events import BatchEvent
from app.models.batch_relations import BatchRelation
from app.models.farm import Farm
from app.models.lot import Lot
from app.models.product import Product
from app.schemas.batch_split import SplitChildPayload
from app.services import batch_relations_service
from tests.conftest import IdentityFixture


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def _login(client: AsyncClient, identity: IdentityFixture) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": identity.email, "password": identity.password},
    )
    assert response.status_code == 200, response.text


def _make_farm(db: Session, organization_id) -> Farm:
    farm = Farm(
        organization_id=organization_id,
        name=f"split-test-farm-{uuid4().hex[:8]}",
        area_ha=Decimal("5.0"),
        latitude=Decimal("10.762622"),
        longitude=Decimal("106.660172"),
    )
    db.add(farm)
    db.commit()
    return farm


def _make_principal(identity: IdentityFixture) -> Principal:
    return Principal(
        user_id=identity.user_id,
        email=identity.email,
        full_name="Test user",
        organization_id=identity.organization_id,
        organization_name="Test org",
        organization_type="farm",
        role="grower",
    )


def _cleanup_lots(db: Session, lot_ids: list) -> None:
    """Delete lots and cascade relations/events."""
    if not lot_ids:
        return
    with db.begin_nested():
        db.execute(text("ALTER TABLE batch_events DISABLE TRIGGER USER"))
        db.execute(text("ALTER TABLE batch_relations DISABLE TRIGGER USER"))
        db.execute(delete(BatchEvent).where(BatchEvent.batch_id.in_(lot_ids)))
        db.execute(
            delete(BatchRelation).where(
                BatchRelation.parent_batch_id.in_(lot_ids)
                | BatchRelation.child_batch_id.in_(lot_ids)
            )
        )
        db.execute(delete(Lot).where(Lot.id.in_(lot_ids)))
        db.execute(text("ALTER TABLE batch_events ENABLE TRIGGER USER"))
        db.execute(text("ALTER TABLE batch_relations ENABLE TRIGGER USER"))
    db.commit()


@pytest.mark.asyncio
async def test_split_lot_happy_path_creates_children_and_events(
    admin_session: Session, identity_factory
):
    """Verify split creates children, batch_relations, and batch_events."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)
    product = Product(name=f"test-product-{uuid4().hex[:8]}", unit="kg")

    # Create parent lot: 100 kg
    parent = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Parent 100kg",
        lot_code=f"P{uuid4().hex[:7].upper()}",
        product_id=None,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
    )
    admin_session.add_all([product, parent])
    admin_session.commit()

    principal = _make_principal(owner)

    # Split into 3 children: 50 + 30 + 10 = 90 kg (remainder 10 kg)
    children_payload = [
        SplitChildPayload(name="Child-50kg", quantity=Decimal("50")),
        SplitChildPayload(name="Child-30kg", quantity=Decimal("30")),
        SplitChildPayload(name="Child-10kg", quantity=Decimal("10")),
    ]

    result = batch_relations_service.split_lot(
        admin_session, principal, parent.id, children_payload
    )

    # Verify transaction created
    assert result["transaction_id"]
    assert result["parent_id"] == parent.id
    assert len(result["children"]) == 3

    # Verify children properties
    for child in result["children"]:
        assert child.parent_batch_id == parent.id
        assert child.lineage_depth == 1
        assert child.root_harvest_id == parent.id  # Parent is root
        assert child.status == "active"
        admin_session.refresh(child)
        assert child.organization_id == owner.organization_id

    # Verify batch_relations created
    relations = admin_session.scalars(
        select(BatchRelation).where(BatchRelation.parent_batch_id == parent.id)
    ).all()
    assert len(relations) == 3
    for rel in relations:
        assert rel.op_type == "split"
        assert rel.weight_transferred in (Decimal("50"), Decimal("30"), Decimal("10"))

    # Verify batch_events created (1 split_initiated + 3 created_from_split = 4 total)
    parent_events = admin_session.scalars(
        select(BatchEvent).where(BatchEvent.batch_id == parent.id)
    ).all()
    assert len(parent_events) == 1
    assert parent_events[0].event_type == "split_initiated"
    assert parent_events[0].hash  # Has hash
    assert parent_events[0].prev_hash == "0" * 64  # Genesis

    child_events = admin_session.scalars(
        select(BatchEvent).where(
            BatchEvent.batch_id.in_([c.id for c in result["children"]])
        )
    ).all()
    assert len(child_events) == 3
    for evt in child_events:
        assert evt.event_type == "created_from_split"
        assert evt.hash

    _cleanup_lots(admin_session, [parent.id] + [c.id for c in result["children"]])


@pytest.mark.asyncio
async def test_split_lot_rejects_mass_conservation_violation(
    admin_session: Session, identity_factory
):
    """Split should reject if Σ(children) > remaining_quantity."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)

    # Parent: 100 kg
    parent = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Parent 100kg",
        lot_code=f"P{uuid4().hex[:7].upper()}",
        product_id=None,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
    )
    admin_session.add(parent)
    admin_session.commit()

    principal = _make_principal(owner)

    # Attempt split: 60 + 50 = 110 > 100 (violation)
    children_payload = [
        SplitChildPayload(name="C1", quantity=Decimal("60")),
        SplitChildPayload(name="C2", quantity=Decimal("50")),
    ]

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        batch_relations_service.split_lot(
            admin_session, principal, parent.id, children_payload
        )
    assert exc_info.value.status_code == 409  # Conflict

    _cleanup_lots(admin_session, [parent.id])


@pytest.mark.asyncio
async def test_split_lot_via_api_endpoint(admin_session: Session, identity_factory):
    """Test split via HTTP POST /lots/{id}/split."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)
    product = Product(name=f"test-product-{uuid4().hex[:8]}", unit="kg")

    parent = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Parent",
        lot_code=f"P{uuid4().hex[:7].upper()}",
        product_id=product.id,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
    )
    admin_session.add_all([product, parent])
    admin_session.commit()

    async with _client() as client:
        await _login(client, owner)

        response = await client.post(
            f"/api/v1/lots/{parent.id}/split",
            json={
                "children": [
                    {"name": "Child-50", "quantity": "50"},
                    {"name": "Child-30", "quantity": "30"},
                    {"name": "Child-20", "quantity": "20"},
                ],
                "note": None,
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "transaction_id" in data
    assert data["parent_id"] == str(parent.id)
    assert len(data["children"]) == 3

    _cleanup_lots(admin_session, [parent.id] + [c["id"] for c in data["children"]])


@pytest.mark.asyncio
async def test_trace_lot_origin_to_root_harvest(
    admin_session: Session, identity_factory
):
    """Trace child → parent → root via lineage."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)

    # Create root harvest lot
    root = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Root harvest",
        lot_code=f"R{uuid4().hex[:7].upper()}",
        product_id=None,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
        parent_batch_id=None,
        lineage_depth=0,
        root_harvest_id=None,  # Will be set to self after creation
    )
    admin_session.add(root)
    admin_session.flush()
    root.root_harvest_id = root.id
    admin_session.commit()

    principal = _make_principal(owner)

    # Split root into child
    children_payload = [
        SplitChildPayload(name="Child-50", quantity=Decimal("50")),
    ]
    result = batch_relations_service.split_lot(
        admin_session, principal, root.id, children_payload
    )
    child = result["children"][0]

    # Trace child back to root
    origin = batch_relations_service.trace_to_root_harvest(
        admin_session, principal, child.id
    )
    assert origin["root_harvest_id"] == root.id
    assert origin["lineage_depth"] == 1

    _cleanup_lots(admin_session, [root.id, child.id])


@pytest.mark.asyncio
async def test_get_batch_children_returns_direct_children_only(
    admin_session: Session, identity_factory
):
    """get_batch_children should return direct children, not grandchildren."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)

    # Create parent
    parent = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Parent",
        lot_code=f"P{uuid4().hex[:7].upper()}",
        product_id=None,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
    )
    admin_session.add(parent)
    admin_session.commit()

    principal = _make_principal(owner)

    # Split parent → 2 children
    children_payload = [
        SplitChildPayload(name="C1", quantity=Decimal("50")),
        SplitChildPayload(name="C2", quantity=Decimal("50")),
    ]
    result1 = batch_relations_service.split_lot(
        admin_session, principal, parent.id, children_payload
    )
    child1, child2 = result1["children"]

    # Get children of parent
    children_of_parent = batch_relations_service.get_batch_children(
        admin_session, principal, parent.id
    )
    assert len(children_of_parent) == 2
    assert {c.id for c in children_of_parent} == {child1.id, child2.id}

    _cleanup_lots(admin_session, [parent.id, child1.id, child2.id])


@pytest.mark.asyncio
async def test_batch_events_immutability_prevents_update_delete(
    admin_session: Session, identity_factory
):
    """Verify batch_events table has BEFORE UPDATE/DELETE triggers."""
    owner = identity_factory()
    farm = _make_farm(admin_session, owner.organization_id)

    parent = Lot(
        organization_id=owner.organization_id,
        current_holder_organization_id=owner.organization_id,
        farm_id=farm.id,
        name="Parent",
        lot_code=f"P{uuid4().hex[:7].upper()}",
        product_id=None,
        harvested_on=date.today(),
        quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        status="active",
    )
    admin_session.add(parent)
    admin_session.commit()

    principal = _make_principal(owner)

    children_payload = [
        SplitChildPayload(name="C1", quantity=Decimal("100")),
    ]
    result = batch_relations_service.split_lot(
        admin_session, principal, parent.id, children_payload
    )

    # Retrieve event
    event = admin_session.scalar(
        select(BatchEvent).where(BatchEvent.batch_id == parent.id)
    )
    assert event

    # Attempt UPDATE → should raise exception
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

    try:
        event.payload = {"tampered": True}
        admin_session.commit()
        pytest.fail("Expected exception when updating batch_events")
    except (SQLAlchemyIntegrityError, DBAPIError):
        admin_session.rollback()  # Expected

    # Attempt DELETE → should raise exception
    try:
        admin_session.delete(event)
        admin_session.commit()
        pytest.fail("Expected exception when deleting batch_events")
    except (SQLAlchemyIntegrityError, DBAPIError):
        admin_session.rollback()  # Expected

    _cleanup_lots(admin_session, [parent.id] + [c.id for c in result["children"]])
