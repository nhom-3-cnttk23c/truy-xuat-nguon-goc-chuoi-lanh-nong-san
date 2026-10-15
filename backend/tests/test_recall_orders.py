"""Test suite for N3-49: Recall order opening, RBAC permissions, and immutable event logging."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.recall import RecallCreate
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login

lineage_products = fixtures.lineage_products


def test_recall_create_schema_validation():
    """Verify non-functional requirement: reason is required and >= 20 characters."""
    valid_reason = "Lô hàng bị phát hiện nhiễm khuẩn E. coli vượt ngưỡng."
    payload = RecallCreate(lot_id=uuid4(), reason=valid_reason)
    assert payload.reason == valid_reason

    # Too short (< 20 chars)
    with pytest.raises(ValidationError):
        RecallCreate(lot_id=uuid4(), reason="Lý do quá ngắn")

    # Whitespace only or trimmed < 20 chars
    with pytest.raises(ValidationError):
        RecallCreate(lot_id=uuid4(), reason="   ngắn   ")


@pytest.mark.asyncio
async def test_inspector_can_open_recall_and_records_immutable_event(
    request, admin_session
):
    """AC1: Inspector opens recall with reason, gets unique recall_code, and lot records event."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    holder = identities(role="cooperative", organization_type="cooperative")
    inspector = identities(role="inspector", organization_type="inspection")
    lot = add_lot(admin_session, holder, products[0])

    reason = "Phát hiện tồn dư thuốc bảo vệ thực vật vượt ngưỡng an toàn thực phẩm."

    async with client() as api:
        await login(api, inspector)

        # Open recall order
        res = await api.post(
            "/api/v1/recalls/",
            json={"lot_id": str(lot.id), "reason": reason},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["root_lot_id"] == str(lot.id)
        assert data["status"] == "open"
        assert data["recall_code"].startswith("RC-")
        assert data["reason"] == reason
        recall_id = data["id"]
        recall_code = data["recall_code"]

        # AC1: Check lot event chain has recall_opened
        history_res = await api.get(f"/api/v1/events/lots/{lot.id}/history")
        assert history_res.status_code == 200, history_res.text
        history_data = history_res.json()
        assert history_data["integrity"]["valid"] is True

        event_types = [e["event_type"] for e in history_data["events"]]
        assert "recall_opened" in event_types

        recall_event = next(
            e for e in history_data["events"] if e["event_type"] == "recall_opened"
        )
        assert recall_event["payload"]["recall_id"] == recall_id
        assert recall_event["payload"]["recall_code"] == recall_code
        assert recall_event["payload"]["reason"] == reason


@pytest.mark.asyncio
async def test_organization_admin_of_holding_org_can_open_recall(
    request, admin_session
):
    """AC1: Organization admin of organization currently holding the lot can open recall."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    admin = identities(role="organization_admin", organization_type="cooperative")
    lot = add_lot(admin_session, admin, products[0])

    reason = "Tự kiểm định phát hiện sản phẩm bị mốc do nhiệt độ bảo quản không đạt."

    async with client() as api:
        await login(api, admin)
        res = await api.post(
            "/api/v1/recalls/",
            json={"lot_id": str(lot.id), "reason": reason},
        )
        assert res.status_code == 201, res.text
        assert res.json()["root_lot_id"] == str(lot.id)
        assert res.json()["status"] == "open"


@pytest.mark.asyncio
async def test_organization_admin_of_other_org_cannot_open_recall(
    request, admin_session
):
    """AC1 & AC2: Organization admin cannot open recall for lots held by other organizations."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    holder = identities(role="grower", organization_type="farm")
    other_admin = identities(
        role="organization_admin", organization_type="distribution"
    )
    lot = add_lot(admin_session, holder, products[0])

    reason = "Yêu cầu thu hồi nhưng tổ chức không nắm giữ lô hàng này."

    async with client() as api:
        await login(api, other_admin)
        res = await api.post(
            "/api/v1/recalls/",
            json={"lot_id": str(lot.id), "reason": reason},
        )
        assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_unauthorized_roles_get_403_when_opening_recall(request, admin_session):
    """AC2: Roles without recalls:open permission (grower, cooperative, distributor) get 403."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    for role, kind in [
        ("grower", "farm"),
        ("cooperative", "cooperative"),
        ("distributor", "distribution"),
    ]:
        user = identities(role=role, organization_type=kind)
        lot = add_lot(admin_session, user, products[0])

        async with client() as api:
            await login(api, user)
            res = await api.post(
                "/api/v1/recalls/",
                json={
                    "lot_id": str(lot.id),
                    "reason": "Phát hiện lỗi kỹ thuật cần mở lệnh thu hồi khẩn cấp.",
                },
            )
            assert res.status_code == 403, (
                f"Expected 403 for {role}, got {res.status_code}"
            )


@pytest.mark.asyncio
async def test_opening_recall_on_lot_with_existing_open_recall_is_blocked(
    request, admin_session
):
    """AC3: If lot already has an open recall, subsequent recall requests are blocked (409) and point to existing."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    holder = identities(role="cooperative", organization_type="cooperative")
    inspector = identities(role="inspector", organization_type="inspection")
    lot = add_lot(admin_session, holder, products[0])

    reason1 = "Lần mở lệnh 1: Phát hiện nhiễm độc tố nấm mốc aflatoxin."
    reason2 = "Lần mở lệnh 2: Phát hiện thêm dư lượng kim loại nặng chì."

    async with client() as api:
        await login(api, inspector)

        # First recall
        first_res = await api.post(
            "/api/v1/recalls/",
            json={"lot_id": str(lot.id), "reason": reason1},
        )
        assert first_res.status_code == 201, first_res.text
        first_id = first_res.json()["id"]
        first_code = first_res.json()["recall_code"]

        # Second recall attempt on the same lot
        second_res = await api.post(
            "/api/v1/recalls/",
            json={"lot_id": str(lot.id), "reason": reason2},
        )
        assert second_res.status_code == 409, second_res.text
        error_detail = second_res.json()["detail"]
        assert error_detail["code"] == "RECALL_ALREADY_OPEN"
        assert error_detail["recall_id"] == first_id
        assert error_detail["recall_code"] == first_code


@pytest.mark.asyncio
async def test_recall_listing_and_get_details(request, admin_session):
    """Verify inspector and organization can list and retrieve recall details."""
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")

    holder = identities(role="cooperative", organization_type="cooperative")
    inspector = identities(role="inspector", organization_type="inspection")
    lot = add_lot(admin_session, holder, products[0])

    async with client() as api:
        await login(api, inspector)

        open_res = await api.post(
            "/api/v1/recalls/",
            json={
                "lot_id": str(lot.id),
                "reason": "Nhiễm vi sinh vật gây hại đường tiêu hóa cần thu hồi.",
            },
        )
        assert open_res.status_code == 201
        recall_id = open_res.json()["id"]

        # List recalls
        list_res = await api.get("/api/v1/recalls/")
        assert list_res.status_code == 200
        recalls = list_res.json()
        assert any(r["id"] == recall_id for r in recalls)

        # Get details
        detail_res = await api.get(f"/api/v1/recalls/{recall_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["id"] == recall_id

        # Non-existent recall
        not_found = await api.get(f"/api/v1/recalls/{uuid4()}")
        assert not_found.status_code == 404
