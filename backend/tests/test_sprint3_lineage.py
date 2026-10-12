"""Sprint 3 transformations must preserve mass, custody and atomic event chains."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.main import app
from app.models.event import Event
from app.models.lot import Lot
from app.models.product import Product
from app.services import event_service
from tests.lineage_helpers import add_lot, client, login, merge_body, split_body


@pytest.fixture
def lineage_products(admin_session):
    products = [
        Product(name=f"lineage-product-{uuid4().hex}", unit="kg") for _ in range(2)
    ]
    admin_session.add_all(products)
    admin_session.commit()
    yield products
    admin_session.execute(
        delete(Product).where(Product.id.in_([p.id for p in products]))
    )
    admin_session.commit()


@pytest.fixture
def lineage(request, admin_session):
    # Set up products first: identity_factory then tears down all lots before products.
    products = request.getfixturevalue("lineage_products")
    identities = request.getfixturevalue("identity_factory")
    owner = identities(role="cooperative", organization_type="cooperative")
    return owner, products, identities


def assert_mass(db, lot_id, expected, status="active"):
    db.expire_all()
    lot = db.get(Lot, lot_id)
    assert lot.remaining_quantity == Decimal(expected)
    assert lot.status == status


def relations(db, child_id):
    return (
        db.execute(
            text(
                "SELECT parent_lot_id, child_lot_id, quantity, operation FROM lot_relations "
                "WHERE child_lot_id = :child_id"
            ),
            {"child_id": child_id},
        )
        .mappings()
        .all()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantities,remaining,status",
    [
        (("10.001", "9.999"), "20.000", "active"),
        (("10.001", "29.999"), "0.000", "closed"),
    ],
)
async def test_split_conserves_decimal_mass_and_logs_both_sides(
    lineage, admin_session, quantities, remaining, status
):
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            f"/api/v1/lots/{parent.id}/split", json=split_body(*quantities)
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["parent"]["id"] == str(parent.id)
        assert len(result["children"]) == 2
        assert_mass(admin_session, parent.id, remaining, status)
        for child, quantity in zip(result["children"], quantities, strict=True):
            child_id = UUID(child["id"])
            assert Decimal(str(child["quantity"])) == Decimal(quantity)
            assert child["product_id"] == str(products[0].id)
            assert child["current_holder_organization_id"] == str(owner.organization_id)
            assert_mass(admin_session, child_id, quantity)
            (edge,) = relations(admin_session, child_id)
            assert edge["parent_lot_id"] == parent.id
            assert edge["quantity"] == Decimal(quantity)
            assert edge["operation"] == "split"
        for lot_id in [parent.id, *(UUID(c["id"]) for c in result["children"])]:
            history = await api.get(f"/api/v1/events/lots/{lot_id}/history")
            assert history.status_code == 200, history.text
            assert history.json()["integrity"]["valid"] is True
            assert history.json()["events"], (
                "Transformation needs an immutable event on every lot"
            )
            expected_type = "lot_split" if lot_id == parent.id else "lot_derived"
            assert history.json()["events"][-1]["event_type"] == expected_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,amount",
    [
        ("pending_handover", "1"),
        ("closed", "1"),
        ("active", "40.001"),
    ],
)
async def test_split_rejects_unavailable_stock_without_writing(
    lineage, admin_session, status, amount
):
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0], status=status)
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            f"/api/v1/lots/{parent.id}/split", json=split_body(amount)
        )
    assert response.status_code == 409, response.text
    assert_mass(admin_session, parent.id, "40", status)
    assert not admin_session.scalars(
        select(Event).where(Event.lot_id == parent.id)
    ).all()


@pytest.mark.asyncio
async def test_split_denies_foreign_holder_and_grower(lineage, admin_session):
    owner, products, identities = lineage
    parent = add_lot(admin_session, owner, products[0])
    outsider = identities(role="distributor", organization_type="distribution")
    grower = identities()
    own_grower_lot = add_lot(admin_session, grower, products[0])
    for identity, lot in [(outsider, parent), (grower, own_grower_lot)]:
        async with client() as api:
            await login(api, identity)
            response = await api.post(
                f"/api/v1/lots/{lot.id}/split", json=split_body("1")
            )
        assert response.status_code == 403, response.text
        assert_mass(admin_session, lot.id, "40")


@pytest.mark.asyncio
async def test_receiver_can_split_original_farm_lot_after_real_handover(
    lineage, admin_session
):
    receiver, products, identities = lineage
    grower = identities()
    parent = add_lot(admin_session, grower, products[0])
    async with client() as sender_api, client() as receiver_api:
        await login(sender_api, grower)
        await login(receiver_api, receiver)
        handover = await sender_api.post(
            "/api/v1/handovers/",
            json={
                "lot_id": str(parent.id),
                "to_organization_id": str(receiver.organization_id),
            },
        )
        assert handover.status_code == 201, handover.text
        accepted = await receiver_api.post(
            f"/api/v1/handovers/{handover.json()['id']}/accept"
        )
        assert accepted.status_code == 200, accepted.text
        result = await receiver_api.post(
            f"/api/v1/lots/{parent.id}/split", json=split_body("30")
        )
        assert result.status_code == 201, result.text
        child = result.json()["children"][0]
        assert child["current_holder_organization_id"] == str(receiver.organization_id)
        assert_mass(admin_session, parent.id, "10")
        history = await receiver_api.get(f"/api/v1/events/lots/{parent.id}/history")
        assert history.status_code == 200, history.text
        assert history.json()["integrity"]["valid"] is True
        assert len(history.json()["events"]) >= 3
        assert history.json()["events"][-1]["event_type"] == "lot_split"


@pytest.mark.asyncio
async def test_merge_consumes_exact_parent_portions(lineage, admin_session):
    owner, products, _ = lineage
    parents = [add_lot(admin_session, owner, products[0]) for _ in range(2)]
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge",
            json=merge_body(
                (parents[0], "10.001"),
                (parents[1], "40"),
            ),
        )
        assert response.status_code == 201, response.text
        child_id = UUID(response.json()["id"])
        assert_mass(admin_session, child_id, "50.001")
        edges = relations(admin_session, child_id)
        assert {(e["parent_lot_id"], e["quantity"], e["operation"]) for e in edges} == {
            (parents[0].id, Decimal("10.001"), "merge"),
            (parents[1].id, Decimal("40"), "merge"),
        }
        for lot_id in [child_id, *(p.id for p in parents)]:
            history = await api.get(f"/api/v1/events/lots/{lot_id}/history")
            assert history.status_code == 200, history.text
            assert history.json()["events"]
            assert history.json()["integrity"]["valid"] is True
            expected_type = "lot_derived" if lot_id == child_id else "lot_merged"
            assert history.json()["events"][-1]["event_type"] == expected_type
    assert_mass(admin_session, parents[0].id, "29.999")
    assert_mass(admin_session, parents[1].id, "0", "closed")


@pytest.mark.asyncio
@pytest.mark.parametrize("different_owner", [False, True])
async def test_merge_rejects_incompatible_product_or_holder(
    lineage, admin_session, different_owner
):
    owner, products, identities = lineage
    other = (
        identities(role="distributor", organization_type="distribution")
        if different_owner
        else owner
    )
    first = add_lot(admin_session, owner, products[0])
    second = add_lot(
        admin_session, other, products[0] if different_owner else products[1]
    )
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge", json=merge_body((first, "1"), (second, "1"))
        )
    assert response.status_code == (403 if different_owner else 422), response.text
    for parent in [first, second]:
        assert_mass(admin_session, parent.id, "40")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["split", "merge"])
async def test_event_failure_rolls_back_mass_children_and_edges(
    lineage, admin_session, monkeypatch, operation
):
    owner, products, _ = lineage
    parents = [add_lot(admin_session, owner, products[0]) for _ in range(2)]
    before_lots = set(admin_session.scalars(select(Lot.id)).all())
    original_append = event_service.append_event

    def append_then_fail(*args, **kwargs):
        original_append(*args, **kwargs)
        raise RuntimeError("lineage event failure")

    async with client() as api:
        await login(api, owner)
        monkeypatch.setattr(event_service, "append_event", append_then_fail)
        with pytest.raises(RuntimeError, match="lineage event failure"):
            if operation == "split":
                await api.post(
                    f"/api/v1/lots/{parents[0].id}/split", json=split_body("10", "20")
                )
            else:
                await api.post(
                    "/api/v1/lots/merge",
                    json=merge_body((parents[0], "10"), (parents[1], "20")),
                )
    admin_session.expire_all()
    assert set(admin_session.scalars(select(Lot.id)).all()) == before_lots
    for parent in parents:
        assert_mass(admin_session, parent.id, "40")
        assert not admin_session.scalars(
            select(Event).where(Event.lot_id == parent.id)
        ).all()
        assert not admin_session.execute(
            text("SELECT id FROM lot_relations WHERE parent_lot_id = :id"),
            {"id": parent.id},
        ).all()


@pytest.mark.parametrize("_attempt", range(20), ids=lambda i: f"race-{i + 1:02}")
def test_concurrent_split_allows_only_one_thirty_from_forty(
    lineage, admin_session, _attempt
):
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])
    parent_id = (
        parent.id
    )  # Never access an expired admin-session ORM object in workers.
    barrier = Barrier(2)

    def transform():
        with TestClient(app, base_url="https://testserver") as api:
            logged_in = api.post(
                "/api/v1/auth/login",
                json={
                    "email": owner.email,
                    "password": owner.password,
                },
            )
            assert logged_in.status_code == 200, logged_in.text
            barrier.wait(timeout=10)
            return api.post(f"/api/v1/lots/{parent_id}/split", json=split_body("30"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: transform(), range(2)))
    assert sorted(r.status_code for r in results) == [201, 409], [
        r.text for r in results
    ]
    assert_mass(admin_session, parent.id, "10")
    successful = next(r for r in results if r.status_code == 201).json()
    assert len(successful["children"]) == 1
    assert_mass(admin_session, UUID(successful["children"][0]["id"]), "30")


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "1.0001", True])
async def test_split_and_merge_reject_invalid_quantities(
    lineage, admin_session, quantity
):
    owner, products, _ = lineage
    parents = [add_lot(admin_session, owner, products[0]) for _ in range(2)]
    async with client() as api:
        await login(api, owner)
        split = await api.post(
            f"/api/v1/lots/{parents[0].id}/split", json=split_body(quantity)
        )
        merge = await api.post(
            "/api/v1/lots/merge",
            json=merge_body((parents[0], quantity), (parents[1], "1")),
        )
    assert split.status_code == 422, split.text
    assert merge.status_code == 422, merge.text
    for parent in parents:
        assert_mass(admin_session, parent.id, "40")


@pytest.mark.asyncio
async def test_merge_rejects_repeated_parent_without_consuming_twice(
    lineage, admin_session
):
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge", json=merge_body((parent, "10"), (parent, "10"))
        )
    assert response.status_code == 422, response.text
    assert_mass(admin_session, parent.id, "40")


@pytest.mark.asyncio
async def test_n340_split_fifty_from_forty_fails_with_remaining_notice(
    lineage, admin_session
):
    """N3-40 AC1: Giả sử lô mẹ còn 40 kg, Khi tách với tổng 50 kg, Thì bị chặn kèm thông báo nêu phần còn lại."""
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            f"/api/v1/lots/{parent.id}/split", json=split_body("50")
        )
    assert response.status_code == 409, response.text
    error_detail = response.json()["detail"]
    assert "chỉ còn 40.000" in error_detail
    assert "vượt quá lượng còn lại" in error_detail
    assert_mass(admin_session, parent.id, "40")


@pytest.mark.asyncio
async def test_n340_concurrent_split_pytest_asyncio_two_connections(
    lineage, admin_session
):
    """N3-40 AC2 & Image 2: Stress test với pytest-asyncio + 2 connections song song trên cùng parent."""
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])
    async with client() as api1, client() as api2:
        await login(api1, owner)
        await login(api2, owner)

        res1, res2 = await asyncio.gather(
            api1.post(f"/api/v1/lots/{parent.id}/split", json=split_body("30")),
            api2.post(f"/api/v1/lots/{parent.id}/split", json=split_body("30")),
        )

    statuses = sorted([res1.status_code, res2.status_code])
    assert statuses == [201, 409], f"res1: {res1.text}, res2: {res2.text}"

    failed_response = res1 if res1.status_code == 409 else res2
    assert "chỉ còn 10.000" in failed_response.text
    assert "vượt quá lượng còn lại" in failed_response.text

    # Parent lot remaining must be exactly 10 kg
    assert_mass(admin_session, parent.id, "10.000")


@pytest.mark.asyncio
async def test_n340_successive_splits_mass_conservation_exact_to_gram(
    lineage, admin_session
):
    """N3-40 AC3: Tách nhiều lần liên tiếp, tổng khối lượng mọi lô con bằng đúng khối lượng đã trừ khỏi lô mẹ, không lệch một gram."""
    owner, products, _ = lineage
    parent = add_lot(admin_session, owner, products[0])  # 40.000 kg
    splits = [
        ("12.345", "27.655", "active"),
        ("7.655", "20.000", "active"),
        ("20.000", "0.000", "closed"),
    ]
    all_children_quantities: list[Decimal] = []

    async with client() as api:
        await login(api, owner)
        for split_amount, expected_parent_remaining, expected_status in splits:
            response = await api.post(
                f"/api/v1/lots/{parent.id}/split", json=split_body(split_amount)
            )
            assert response.status_code == 201, response.text
            created_child = response.json()["children"][0]
            child_qty = Decimal(str(created_child["quantity"]))
            all_children_quantities.append(child_qty)
            assert_mass(
                admin_session, parent.id, expected_parent_remaining, expected_status
            )

    # Tổng mọi lô con = đúng 40.000 kg, không lệch một gram
    assert sum(all_children_quantities) == Decimal("40.000")
    assert_mass(admin_session, parent.id, "0.000", "closed")


@pytest.mark.asyncio
async def test_n341_merge_three_parents_all_mass_creates_single_child_and_closes_all_parents(
    lineage, admin_session
):
    """N3-41 AC1: Giữ ba lô cùng sản phẩm, gộp toàn bộ -> một lô mới ghi rõ cả ba lô mẹ, ba lô mẹ còn lại 0 kg (closed)."""
    owner, products, _ = lineage
    parents = [add_lot(admin_session, owner, products[0]) for _ in range(3)]
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge",
            json=merge_body(
                (parents[0], "40.000"),
                (parents[1], "40.000"),
                (parents[2], "40.000"),
            ),
        )
        assert response.status_code == 201, response.text
        child_data = response.json()
        child_id = UUID(child_data["id"])

        # Lô con nhận đủ 120.000 kg
        assert_mass(admin_session, child_id, "120.000", "active")

        # Cả ba lô mẹ còn lại đúng 0.000 kg và chuyển trạng thái closed
        for parent in parents:
            assert_mass(admin_session, parent.id, "0.000", "closed")

        # Quan hệ phả hệ ghi rõ cả 3 lô mẹ
        edges = relations(admin_session, child_id)
        assert len(edges) == 3
        assert {(e["parent_lot_id"], e["quantity"], e["operation"]) for e in edges} == {
            (parents[0].id, Decimal("40.000"), "merge"),
            (parents[1].id, Decimal("40.000"), "merge"),
            (parents[2].id, Decimal("40.000"), "merge"),
        }

        # Kiểm tra event chain của lô mới và cả ba lô mẹ
        for lot_id in [child_id, *(p.id for p in parents)]:
            history = await api.get(f"/api/v1/events/lots/{lot_id}/history")
            assert history.status_code == 200, history.text
            assert history.json()["integrity"]["valid"] is True
            expected_type = "lot_derived" if lot_id == child_id else "lot_merged"
            assert history.json()["events"][-1]["event_type"] == expected_type


@pytest.mark.asyncio
async def test_n341_merge_partial_quantities_deducts_exact_portions(
    lineage, admin_session
):
    """N3-41 AC2: Gộp một phần của mỗi lô -> lô mới có khối lượng bằng tổng phần lấy, mỗi lô mẹ trừ đúng phần đó."""
    owner, products, _ = lineage
    parents = [add_lot(admin_session, owner, products[0]) for _ in range(3)]
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge",
            json=merge_body(
                (parents[0], "12.345"),
                (parents[1], "10.000"),
                (parents[2], "7.655"),
            ),
        )
        assert response.status_code == 201, response.text
        child_id = UUID(response.json()["id"])

        # Lô mới nhận đúng tổng 30.000 kg
        assert_mass(admin_session, child_id, "30.000", "active")

        # Mỗi lô mẹ trừ đúng phần lấy ra, không lệch một gram
        assert_mass(admin_session, parents[0].id, "27.655", "active")
        assert_mass(admin_session, parents[1].id, "30.000", "active")
        assert_mass(admin_session, parents[2].id, "32.345", "active")

        # Quan hệ phả hệ ghi nhận trọng số từng phần
        edges = relations(admin_session, child_id)
        assert {(e["parent_lot_id"], e["quantity"], e["operation"]) for e in edges} == {
            (parents[0].id, Decimal("12.345"), "merge"),
            (parents[1].id, Decimal("10.000"), "merge"),
            (parents[2].id, Decimal("7.655"), "merge"),
        }


@pytest.mark.asyncio
async def test_n341_merge_different_products_rejected_with_reason_and_offending_lot(
    lineage, admin_session
):
    """N3-41 AC3: Hai lô khác sản phẩm khi gộp thì bị chặn kèm lý do nêu mã/tên lô vi phạm."""
    owner, products, _ = lineage
    p1 = add_lot(admin_session, owner, products[0])
    p2 = add_lot(admin_session, owner, products[1])
    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge",
            json=merge_body((p1, "10.000"), (p2, "10.000")),
        )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert p2.lot_code in detail or p2.name in detail
    assert "khác nông sản" in detail

    # Khối lượng các lô mẹ không thay đổi
    assert_mass(admin_session, p1.id, "40.000")
    assert_mass(admin_session, p2.id, "40.000")


@pytest.mark.asyncio
async def test_n341_merge_foreign_lot_rejected_with_403(lineage, admin_session):
    """N3-41 AC4: Một trong các lô không do tổ chức mình giữ khi gộp thì bị chặn 403 kèm thông báo."""
    owner, products, identities = lineage
    outsider = identities(role="distributor", organization_type="distribution")
    p1 = add_lot(admin_session, owner, products[0])
    foreign_lot = add_lot(admin_session, outsider, products[0])

    async with client() as api:
        await login(api, owner)
        response = await api.post(
            "/api/v1/lots/merge",
            json=merge_body((p1, "10.000"), (foreign_lot, "10.000")),
        )
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert "chỉ được xử lý lô do tổ chức mình" in detail

    # Khối lượng các lô không thay đổi
    assert_mass(admin_session, p1.id, "40.000")
    assert_mass(admin_session, foreign_lot.id, "40.000")


@pytest.mark.asyncio
async def test_n341_concurrent_cross_merge_no_deadlock(lineage, admin_session):
    """N3-120: Khóa theo thứ tự cố định để hai phép gộp chéo nhau không deadlock / treo giao dịch."""
    owner, products, _ = lineage
    p1 = add_lot(admin_session, owner, products[0])
    p2 = add_lot(admin_session, owner, products[0])

    async with client() as api1, client() as api2:
        await login(api1, owner)
        await login(api2, owner)

        # Tx1 gộp (p1, 20), (p2, 20); Tx2 gộp chéo thứ tự (p2, 20), (p1, 20)
        res1, res2 = await asyncio.gather(
            api1.post(
                "/api/v1/lots/merge",
                json=merge_body((p1, "20.000"), (p2, "20.000")),
            ),
            api2.post(
                "/api/v1/lots/merge",
                json=merge_body((p2, "20.000"), (p1, "20.000")),
            ),
        )

    # Nhờ order_by(Lot.id) trong _lock_parents, cả hai giao dịch hoàn tất không bị deadlock
    assert res1.status_code == 201, res1.text
    assert res2.status_code == 201, res2.text

    # Cả hai lô mẹ bị trừ chính xác 20 + 20 = 40 kg, còn lại 0.000 và closed
    assert_mass(admin_session, p1.id, "0.000", "closed")
    assert_mass(admin_session, p2.id, "0.000", "closed")
