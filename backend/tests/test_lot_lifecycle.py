"""Runtime PostgreSQL lifecycle proofs: locations, terminal stock and audit chains."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from app.core.auth import Principal
from app.core.database import SessionLocal, set_db_context
from app.main import app
from app.models.event import Event
from app.models.location import Location
from app.models.lot import Lot
from app.services import event_service, handover_service, traversal_service
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login, split_body

lineage_products = fixtures.lineage_products


@pytest.fixture
def distribution(request):
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")
    owner = identities(role="distributor", organization_type="distribution")
    return owner, products, identities


async def create_location(api, name="Cửa hàng 1"):
    response = await api.post(
        "/api/v1/locations/", json={"name": name, "address": "12 Nguyễn Huệ"}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_internal_move_and_consume_have_valid_immutable_chain(
    distribution, admin_session
):
    owner, products, _ = distribution
    lot = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        location = await create_location(api)
        moved = await api.post(
            f"/api/v1/lots/{lot.id}/move", json={"location_id": location["id"]}
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["current_location"]["name"] == location["name"]
        assert moved.json()["current_holder_organization_id"] == str(
            owner.organization_id
        )
        consumed = await api.post(
            f"/api/v1/lots/{lot.id}/consume", json={"note": "Đã bán hết"}
        )
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["status"] == "consumed"
        assert Decimal(consumed.json()["remaining_quantity"]) == 0
        history = (await api.get(f"/api/v1/events/lots/{lot.id}/history")).json()
        assert history["integrity"]["valid"]
        assert [item["event_type"] for item in history["events"]] == [
            "lot_moved",
            "lot_consumed",
        ]
        for path, body in [
            (f"/api/v1/lots/{lot.id}/consume", {}),
            (f"/api/v1/lots/{lot.id}/move", {"location_id": location["id"]}),
            (f"/api/v1/lots/{lot.id}/split", split_body("1")),
            ("/api/v1/events/", {"lot_id": str(lot.id), "event_type": "manual"}),
        ]:
            blocked = await api.post(path, json=body)
            assert blocked.status_code == 409, blocked.text
    assert (
        len(admin_session.scalars(select(Event).where(Event.lot_id == lot.id)).all())
        == 2
    )


@pytest.mark.asyncio
async def test_split_assigns_only_current_organization_locations(
    distribution, admin_session
):
    owner, products, identities = distribution
    foreign = identities(role="distributor", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])
    async with client() as api, client() as other:
        await login(api, owner)
        await login(other, foreign)
        own_location = await create_location(api)
        foreign_location = await create_location(other)
        body = split_body("10", "10")
        body["children"][1]["location_id"] = foreign_location["id"]
        denied = await api.post(f"/api/v1/lots/{lot.id}/split", json=body)
        assert denied.status_code == 403, denied.text
        admin_session.expire_all()
        assert admin_session.get(Lot, lot.id).remaining_quantity == Decimal("40")
        body["children"][1]["location_id"] = own_location["id"]
        result = await api.post(f"/api/v1/lots/{lot.id}/split", json=body)
        assert result.status_code == 201, result.text
        assert result.json()["children"][0]["current_location"] is None
        assert (
            result.json()["children"][1]["current_location"]["id"] == own_location["id"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,org_type",
    [
        ("organization_admin", "farm"),
        ("distributor", "farm"),
        ("cooperative", "distribution"),
        ("inspector", "distribution"),
        ("system_admin", "distribution"),
    ],
)
async def test_location_and_consume_reject_wrong_role_or_organization(
    distribution, admin_session, role, org_type
):
    _, products, identities = distribution
    identity = identities(role=role, organization_type=org_type)
    lot = add_lot(admin_session, identity, products[0])
    async with client() as api:
        await login(api, identity)
        assert (
            await api.post(
                "/api/v1/locations/", json={"name": "Kho", "address": "Địa chỉ"}
            )
        ).status_code == 403
        assert (
            await api.post(f"/api/v1/lots/{lot.id}/consume", json={})
        ).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["move", "consume"])
async def test_event_failure_rolls_back_location_and_consumption(
    distribution, admin_session, monkeypatch, operation
):
    owner, products, _ = distribution
    lot = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        location = await create_location(api)
        original = event_service.append_event

        def fail_after_event(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("lifecycle event failure")

        monkeypatch.setattr(event_service, "append_event", fail_after_event)
        with pytest.raises(RuntimeError, match="lifecycle event failure"):
            await api.post(
                f"/api/v1/lots/{lot.id}/{operation}",
                json={"location_id": location["id"]},
            )
    admin_session.expire_all()
    stored = admin_session.get(Lot, lot.id)
    assert stored.status == "active" and stored.remaining_quantity == Decimal("40")
    assert stored.current_location_id is None
    assert not admin_session.scalars(select(Event).where(Event.lot_id == lot.id)).all()


@pytest.mark.asyncio
async def test_locations_rls_and_composite_fk_isolate_organizations(
    distribution, admin_session
):
    owner, products, identities = distribution
    foreign = identities(role="distributor", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])
    async with client() as owner_api, client() as foreign_api:
        await login(owner_api, owner)
        await login(foreign_api, foreign)
        location = await create_location(owner_api)
        assert (await foreign_api.get("/api/v1/locations/")).json() == []
        assert (
            await foreign_api.post(f"/api/v1/lots/{lot.id}/consume", json={})
        ).status_code == 403
        with SessionLocal() as db:
            set_db_context(db, session_token_hash=foreign.session_token_hash)
            assert db.get(Location, UUID(location["id"])) is None
            with pytest.raises(DBAPIError):
                db.execute(
                    text(
                        "INSERT INTO locations (id, organization_id, name, address) VALUES (gen_random_uuid(), :org, 'forged', 'address')"
                    ),
                    {"org": owner.organization_id},
                )
            db.rollback()
        with pytest.raises(DBAPIError):
            admin_session.execute(
                text(
                    "UPDATE lots SET current_location_id = :location, current_holder_organization_id = :foreign WHERE id = :id"
                ),
                {
                    "location": UUID(location["id"]),
                    "foreign": foreign.organization_id,
                    "id": lot.id,
                },
            )
        admin_session.rollback()


@pytest.mark.asyncio
async def test_distribution_orgadmin_can_manage_locations_and_consume(
    distribution, admin_session
):
    _, products, identities = distribution
    owner = identities(role="organization_admin", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        await create_location(api)
        assert len((await api.get("/api/v1/locations/")).json()) == 1
        assert (
            await api.post(f"/api/v1/lots/{lot.id}/consume", json={})
        ).status_code == 200


@pytest.mark.asyncio
async def test_consumed_is_terminal_in_postgres_and_blocks_all_business_writes(
    distribution, admin_session
):
    owner, products, identities = distribution
    recipient = identities(role="distributor", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])
    other = add_lot(admin_session, owner, products[0])
    lot_id = lot.id
    with pytest.raises(DBAPIError):
        admin_session.execute(
            text("UPDATE lots SET status = 'consumed' WHERE id = :id"), {"id": lot_id}
        )
    admin_session.rollback()
    async with client() as api:
        await login(api, owner)
        assert (
            await api.post(f"/api/v1/lots/{lot_id}/consume", json={})
        ).status_code == 200
        handover = await api.post(
            "/api/v1/handovers/",
            json={
                "lot_id": str(lot_id),
                "to_organization_id": str(recipient.organization_id),
            },
        )
        assert handover.status_code == 409, handover.text
        merged = await api.post(
            "/api/v1/lots/merge",
            json={
                "name": "Forbidden merge",
                "parents": [
                    {"lot_id": str(lot_id), "quantity": "1"},
                    {"lot_id": str(other.id), "quantity": "1"},
                ],
            },
        )
        assert merged.status_code == 409, merged.text
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=owner.session_token_hash)
        with pytest.raises(DBAPIError, match="terminal"):
            db.execute(
                text(
                    "UPDATE lots SET status = 'active', remaining_quantity = 1 WHERE id = :id"
                ),
                {"id": lot_id},
            )
        db.rollback()
        with pytest.raises(DBAPIError, match="consumed lot"):
            db.execute(
                text(
                    "INSERT INTO events(id, organization_id, lot_id, sequence_number, event_type, payload, prev_hash, event_hash) VALUES (gen_random_uuid(), :org, :lot, 2, 'manual', '{}', :hash, :hash)"
                ),
                {"org": owner.organization_id, "lot": lot_id, "hash": "0" * 64},
            )
        db.rollback()


@pytest.mark.parametrize("operation", ["split", "handover"])
def test_concurrent_consume_serializes_with_split_or_handover(
    distribution, admin_session, operation
):
    owner, products, identities = distribution
    recipient = identities(role="distributor", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])
    lot_id = lot.id
    barrier = Barrier(2)

    def run(action):
        with TestClient(app, base_url="https://testserver") as api:
            assert (
                api.post(
                    "/api/v1/auth/login",
                    json={"email": owner.email, "password": owner.password},
                ).status_code
                == 200
            )
            barrier.wait(timeout=10)
            if action == "consume":
                return api.post(f"/api/v1/lots/{lot_id}/consume", json={})
            if action == "split":
                return api.post(f"/api/v1/lots/{lot_id}/split", json=split_body("40"))
            return api.post(
                "/api/v1/handovers/",
                json={
                    "lot_id": str(lot_id),
                    "to_organization_id": str(recipient.organization_id),
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["consume", operation]))
    assert sum(response.status_code in {200, 201} for response in results) == 1, [
        r.text for r in results
    ]
    assert sum(response.status_code == 409 for response in results) == 1
    admin_session.expire_all()
    stored = admin_session.get(Lot, lot_id)
    assert stored.status in {"consumed", "closed", "pending_handover"}
    assert stored.remaining_quantity == (
        Decimal("40") if stored.status == "pending_handover" else 0
    )


@pytest.mark.asyncio
async def test_transfer_clears_location_and_historical_descendants_redact_it(
    distribution, admin_session
):
    owner, products, identities = distribution
    receiver = identities(role="distributor", organization_type="distribution")
    root = add_lot(admin_session, owner, products[0])
    async with client() as api, client() as receiving:
        await login(api, owner)
        await login(receiving, receiver)
        location = await create_location(api)
        body = split_body("10")
        body["children"][0]["location_id"] = location["id"]
        child = (await api.post(f"/api/v1/lots/{root.id}/split", json=body)).json()[
            "children"
        ][0]
        handover = await api.post(
            "/api/v1/handovers/",
            json={
                "lot_id": child["id"],
                "to_organization_id": str(receiver.organization_id),
            },
        )
        accepted = await receiving.post(
            f"/api/v1/handovers/{handover.json()['id']}/accept"
        )
        assert accepted.status_code == 200, accepted.text
        received = (await receiving.get(f"/api/v1/lots/{child['id']}")).json()
        assert (
            received["current_location_id"] is None
            and received["current_location"] is None
        )
        own_location = await create_location(receiving, "Private receiver store")
        assert (
            await receiving.post(
                f"/api/v1/lots/{child['id']}/move",
                json={"location_id": own_location["id"]},
            )
        ).status_code == 200
        historical = (
            await api.get(f"/api/v1/lots/{root.id}/lineage?direction=descendants")
        ).json()
        node = next(item for item in historical["nodes"] if item["id"] == child["id"])
        assert node["historical_only"] and node["status"] == "transferred"
        assert node["current_location_id"] is None and node["current_location"] is None
        assert node["remaining_quantity"] is None


@pytest.mark.asyncio
async def test_inspector_bulk_descendants_include_location_consumption_in_three_data_queries(
    distribution, admin_session
):
    owner, products, identities = distribution
    inspector = identities(role="inspector", organization_type="inspection")
    root = add_lot(admin_session, owner, products[0])
    root_id = root.id
    async with client() as api:
        await login(api, owner)
        location = await create_location(api)
        body = split_body(*(["1"] * 20))
        for child in body["children"]:
            child["location_id"] = location["id"]
        result = await api.post(f"/api/v1/lots/{root_id}/split", json=body)
        assert result.status_code == 201, result.text
        consumed_id = result.json()["children"][0]["id"]
        assert (
            await api.post(f"/api/v1/lots/{consumed_id}/consume", json={})
        ).status_code == 200
    principal = Principal(
        user_id=inspector.user_id,
        email=inspector.email,
        full_name="Inspector",
        organization_id=inspector.organization_id,
        organization_name="Inspection",
        organization_type="inspection",
        role="inspector",
    )
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=inspector.session_token_hash)
        queries = []

        def collect(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", collect)
        try:
            graph = traversal_service.get_lineage(db, principal, root_id, "descendants")
        finally:
            event.remove(connection, "before_cursor_execute", collect)
    # Three data reads remain constant for any node count. The transaction's
    # JIT setting is one additional command, not a per-node data query.
    data_queries = [
        sql for sql in queries if sql.lstrip().startswith(("SELECT", "WITH"))
    ]
    assert len(data_queries) == 3 and len(queries) == 4, queries
    assert len(graph["nodes"]) == 21
    for node in graph["nodes"]:
        assert node["current_holder_organization_name"]
        if node["id"] == root_id:
            continue
        assert node["current_location"]["name"] == location["name"]
        assert node["current_location"]["address"] == location["address"]
        assert not node["historical_only"]
        assert node["status"] == (
            "consumed" if str(node["id"]) == consumed_id else "active"
        )


def test_runtime_non_distribution_actor_cannot_bypass_consume_permission(
    distribution, admin_session
):
    _, products, identities = distribution
    grower = identities()
    lot = add_lot(admin_session, grower, products[0])
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=grower.session_token_hash)
        with pytest.raises(DBAPIError, match="distribution"):
            db.execute(
                text(
                    "UPDATE lots SET status = 'consumed', remaining_quantity = 0 WHERE id = :id"
                ),
                {"id": lot.id},
            )
        db.rollback()


@pytest.mark.parametrize("located", [False, True])
def test_runtime_insert_cannot_bypass_lifecycle(distribution, admin_session, located):
    _, products, identities = distribution
    actor = (
        identities(role="transporter", organization_type="distribution")
        if located
        else identities()
    )
    location = Location(
        organization_id=actor.organization_id, name="Insert guard", address="Store"
    )
    admin_session.add(location)
    admin_session.commit()
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=actor.session_token_hash)
        with pytest.raises(DBAPIError, match="distribution|created consumed"):
            db.execute(
                text("""INSERT INTO lots
                (id, organization_id, current_holder_organization_id, product_id, name,
                 lot_code, quantity, remaining_quantity, status, current_location_id)
                VALUES (:id, :org, :org, :product, 'Bypass', :code, 1, :remaining, :status, :location)"""),
                {
                    "id": uuid4(),
                    "org": actor.organization_id,
                    "product": products[0].id,
                    "code": uuid4().hex[:10],
                    "remaining": 1 if located else 0,
                    "status": "active" if located else "consumed",
                    "location": location.id if located else None,
                },
            )
        db.rollback()


def test_runtime_unauthorized_role_cannot_clear_location(distribution, admin_session):
    _, products, identities = distribution
    transporter = identities(role="transporter", organization_type="distribution")
    location = Location(
        organization_id=transporter.organization_id, name="Store", address="Address"
    )
    admin_session.add(location)
    admin_session.commit()
    lot = add_lot(admin_session, transporter, products[0])
    lot.current_location_id = location.id
    admin_session.commit()
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=transporter.session_token_hash)
        with pytest.raises(DBAPIError, match="distribution"):
            db.execute(
                text("UPDATE lots SET current_location_id = NULL WHERE id = :id"),
                {"id": lot.id},
            )
        db.rollback()


@pytest.mark.asyncio
async def test_acceptance_history_includes_event_even_when_processing_clock_is_earlier(
    distribution, admin_session, monkeypatch
):
    owner, products, identities = distribution
    receiver = identities(role="distributor", organization_type="distribution")
    lot = add_lot(admin_session, owner, products[0])

    class EarlierClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) - timedelta(seconds=1)

    async with client() as sender_api, client() as receiving_api:
        await login(sender_api, owner)
        await login(receiving_api, receiver)
        transfer = await sender_api.post(
            "/api/v1/handovers/",
            json={
                "lot_id": str(lot.id),
                "to_organization_id": str(receiver.organization_id),
            },
        )
        monkeypatch.setattr(handover_service, "datetime", EarlierClock)
        accepted = await receiving_api.post(
            f"/api/v1/handovers/{transfer.json()['id']}/accept"
        )
        assert accepted.status_code == 200, accepted.text
        history = (await sender_api.get(f"/api/v1/events/lots/{lot.id}/history")).json()
        assert [item["event_type"] for item in history["events"]] == [
            "handover_pending",
            "handover_accepted",
        ]
        assert history["integrity"]["valid"]
