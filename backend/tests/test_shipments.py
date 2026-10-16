"""Test suite for N3-58: Cold chain shipments with multiple lots and a refrigerated container."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.shipment import ShipmentCreate
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login

lineage_products = fixtures.lineage_products


def test_shipment_create_schema_validation():
    """Verify schema constraints: container_code is required, lot_ids cannot be empty or have duplicates."""
    lot1 = uuid4()
    lot2 = uuid4()

    valid = ShipmentCreate(container_code="CONT-01", lot_ids=[lot1, lot2])
    assert valid.container_code == "CONT-01"
    assert len(valid.lot_ids) == 2

    # Whitespace container code
    with pytest.raises(ValidationError):
        ShipmentCreate(container_code="   ", lot_ids=[lot1])

    # Empty lot_ids
    with pytest.raises(ValidationError):
        ShipmentCreate(container_code="CONT-01", lot_ids=[])

    # Duplicate lot_ids
    with pytest.raises(ValidationError):
        ShipmentCreate(container_code="CONT-01", lot_ids=[lot1, lot1])


@pytest.mark.asyncio
async def test_transporter_can_open_shipment_with_multiple_lots_and_records_loaded_event(
    request, admin_session
):
    """AC: Transporter opens a shipment for lots they hold, gets shipment code, and events are logged to lots."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    transporter = identities(role="transporter", organization_type="transport")
    lot1 = add_lot(admin_session, transporter, products[0], quantity="50.000")
    lot2 = add_lot(admin_session, transporter, products[1], quantity="30.000")

    container_code = "CONTAINER-COLD-99"

    async with client() as api:
        await login(api, transporter)

        res = await api.post(
            "/api/v1/shipments/",
            json={
                "container_code": container_code,
                "lot_ids": [str(lot1.id), str(lot2.id)],
                "notes": "Vận chuyển nông sản từ Đà Lạt về TP.HCM",
            },
        )
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["status"] == "in_transit"
        assert data["container_code"] == container_code
        assert data["shipment_code"].startswith("SH-")
        assert data["lot_count"] == 2
        assert len(data["lots"]) == 2
        shipment_id = data["id"]
        shipment_code = data["shipment_code"]

        # Verify shipment_loaded event recorded on lot1
        res_events1 = await api.get(f"/api/v1/events/lots/{lot1.id}/history")
        assert res_events1.status_code == 200, res_events1.text
        events1 = res_events1.json()["events"]
        loaded_event1 = next(
            (e for e in events1 if e["event_type"] == "shipment_loaded"), None
        )
        assert loaded_event1 is not None
        assert loaded_event1["payload"]["shipment_id"] == shipment_id
        assert loaded_event1["payload"]["shipment_code"] == shipment_code
        assert loaded_event1["payload"]["container_code"] == container_code
        assert loaded_event1["payload"]["action"] == "loaded_on_vehicle"

        # Verify shipment_loaded event recorded on lot2
        res_events2 = await api.get(f"/api/v1/events/lots/{lot2.id}/history")
        assert res_events2.status_code == 200, res_events2.text
        events2 = res_events2.json()["events"]
        loaded_event2 = next(
            (e for e in events2 if e["event_type"] == "shipment_loaded"), None
        )
        assert loaded_event2 is not None
        assert loaded_event2["payload"]["shipment_id"] == shipment_id


@pytest.mark.asyncio
async def test_transporter_can_complete_shipment_and_records_unloaded_event(
    request, admin_session
):
    """AC: Completing a shipment transitions status to completed and records shipment_unloaded events."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    transporter = identities(role="transporter", organization_type="transport")
    lot = add_lot(admin_session, transporter, products[0], quantity="25.000")

    async with client() as api:
        await login(api, transporter)

        # Open shipment
        open_res = await api.post(
            "/api/v1/shipments/",
            json={
                "container_code": "COLD-BOX-02",
                "lot_ids": [str(lot.id)],
            },
        )
        assert open_res.status_code == 201, open_res.text
        shipment_id = open_res.json()["id"]

        # Complete shipment
        complete_res = await api.post(f"/api/v1/shipments/{shipment_id}/complete")
        assert complete_res.status_code == 200, complete_res.text
        comp_data = complete_res.json()
        assert comp_data["status"] == "completed"
        assert comp_data["completed_at"] is not None

        # Verify lot event history has shipment_unloaded
        history_res = await api.get(f"/api/v1/events/lots/{lot.id}/history")
        assert history_res.status_code == 200, history_res.text
        events = history_res.json()["events"]
        unloaded_event = next(
            (e for e in events if e["event_type"] == "shipment_unloaded"), None
        )
        assert unloaded_event is not None
        assert unloaded_event["payload"]["shipment_id"] == shipment_id
        assert unloaded_event["payload"]["action"] == "unloaded_from_vehicle"


@pytest.mark.asyncio
async def test_lot_cannot_be_in_two_active_shipments_simultaneously(
    request, admin_session
):
    """NFR: một lô chỉ nằm trong một chuyến đang chạy tại một thời điểm."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    transporter = identities(role="transporter", organization_type="transport")
    lot = add_lot(admin_session, transporter, products[0])

    async with client() as api:
        await login(api, transporter)

        # First active shipment
        res1 = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-A", "lot_ids": [str(lot.id)]},
        )
        assert res1.status_code == 201, res1.text
        first_id = res1.json()["id"]

        # Second attempt on the same lot while first is in transit
        res2 = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-B", "lot_ids": [str(lot.id)]},
        )
        assert res2.status_code == 409, res2.text
        detail = res2.json()["detail"]
        assert detail["code"] == "LOT_ALREADY_IN_TRANSIT"

        # Complete first shipment
        comp_res = await api.post(f"/api/v1/shipments/{first_id}/complete")
        assert comp_res.status_code == 200, comp_res.text

        # Now opening a new shipment with this lot succeeds
        res3 = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-C", "lot_ids": [str(lot.id)]},
        )
        assert res3.status_code == 201, res3.text
        assert res3.json()["status"] == "in_transit"


@pytest.mark.asyncio
async def test_cannot_ship_consumed_lot(request, admin_session):
    """Verify terminal consumed lot cannot be placed on a shipment."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    transporter = identities(role="transporter", organization_type="transport")
    consumed_lot = add_lot(
        admin_session, transporter, products[0], quantity="10.000", status="active"
    )
    consumed_lot.remaining_quantity = Decimal("0.000")
    consumed_lot.status = "consumed"
    admin_session.commit()

    async with client() as api:
        await login(api, transporter)
        res = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-X", "lot_ids": [str(consumed_lot.id)]},
        )
        assert res.status_code == 409, res.text


@pytest.mark.asyncio
async def test_cannot_ship_lot_held_by_another_organization(request, admin_session):
    """AC: Transporter can only declare shipments for lots held by their organization."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    grower = identities(role="grower", organization_type="farm")
    transporter = identities(role="transporter", organization_type="transport")
    farm_lot = add_lot(admin_session, grower, products[0])

    async with client() as api:
        await login(api, transporter)
        res = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-OTHER", "lot_ids": [str(farm_lot.id)]},
        )
        assert res.status_code in {403, 404}, res.text


@pytest.mark.asyncio
async def test_unauthorized_role_cannot_create_shipment(request, admin_session):
    """Roles without shipments:create permission cannot open shipments."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    grower = identities(role="grower", organization_type="farm")
    lot = add_lot(admin_session, grower, products[0])

    async with client() as api:
        await login(api, grower)
        res = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-FAIL", "lot_ids": [str(lot.id)]},
        )
        assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_listing_and_getting_shipment_details(request, admin_session):
    """Verify listing and detail retrieval of shipments."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    transporter = identities(role="transporter", organization_type="transport")
    lot = add_lot(admin_session, transporter, products[0])

    async with client() as api:
        await login(api, transporter)

        open_res = await api.post(
            "/api/v1/shipments/",
            json={"container_code": "BOX-LIST", "lot_ids": [str(lot.id)]},
        )
        assert open_res.status_code == 201
        shipment_id = open_res.json()["id"]

        # List shipments
        list_res = await api.get("/api/v1/shipments/")
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(s["id"] == shipment_id for s in items)

        # Get details
        detail_res = await api.get(f"/api/v1/shipments/{shipment_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == shipment_id
        assert detail["container_code"] == "BOX-LIST"
        assert len(detail["lots"]) == 1
        assert detail["lots"][0]["lot_id"] == str(lot.id)
