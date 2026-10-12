"""Measured AC boundaries; fixtures only touch the isolated test database."""

from datetime import date
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, text

from app.core.database import SessionLocal, set_db_context
from app.models.farm import Farm
from app.models.lot import Lot
from app.services import event_service, lot_service
from tests import test_event_integrity as integrity
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login, split_body

lineage = fixtures.lineage
lineage_products = fixtures.lineage_products


@pytest.mark.performance
def test_two_hundred_event_history_one_event_query_under_200ms(
    admin_session, identity_factory
):
    owner = identity_factory()
    farm, product, lot, principal = integrity._create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    try:
        integrity._append_chain(admin_session, principal, lot.id, 200)
        with SessionLocal() as db:
            set_db_context(db, session_token_hash=owner.session_token_hash)
            statements = []
            connection = db.connection()
            # Exercise the nested-loop plan observed on CI: organization RLS
            # must not be re-evaluated once for each event in the history.
            connection.execute(text("SET LOCAL enable_hashjoin = off"))
            connection.execute(text("SET LOCAL enable_mergejoin = off"))
            connection.execute(text("SET LOCAL enable_material = off"))

            def capture(conn, cur, statement, parameters, context, many):
                statements.append((statement, parameters))

            event.listen(connection, "before_cursor_execute", capture)
            started = perf_counter()
            result = event_service.get_event_history(db, principal, lot.id)
            elapsed = perf_counter() - started
            event.remove(connection, "before_cursor_execute", capture)
            assert len(result["events"]) == 200 and result["integrity"]["valid"]
            assert sum("FROM events" in statement for statement, _ in statements) == 1
            history_sql, history_parameters = next(
                (sql, params) for sql, params in statements if "FROM events" in sql
            )
            history_plan = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, FORMAT JSON) " + history_sql, history_parameters
            ).scalar()[0]["Plan"]

            def nodes(plan):
                yield plan
                for child in plan.get("Plans", []):
                    yield from nodes(child)

            organization_scans = [
                node
                for node in nodes(history_plan)
                if node.get("Relation Name") == "organizations"
            ]
            assert organization_scans
            assert all(node["Actual Loops"] <= 1 for node in organization_scans)
            if elapsed >= 0.2:
                statement, parameters = next(
                    item for item in statements if "FROM events" in item[0]
                )
                plan = connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters
                ).scalar()[0]
                print(plan)
            print(
                f"200 events, one event-data query: {elapsed * 1000:.1f}ms; {len(statements)} queries incl. authorization/privacy"
            )
            assert elapsed < 0.2
    finally:
        integrity._cleanup_lot_records(admin_session, farm, product, [lot.id])


@pytest.mark.asyncio
async def test_history_pages_verify_the_complete_501_event_chain(
    admin_session, identity_factory
):
    owner = identity_factory()
    farm, product, lot, principal = integrity._create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    try:
        integrity._append_chain(admin_session, principal, lot.id, 501)
        async with client() as api:
            await login(api, owner)
            first = await api.get(f"/api/v1/events/lots/{lot.id}/history?page_size=500")
            assert first.status_code == 200, first.text
            body = first.json()
            assert len(body["events"]) == 500
            assert body["next_cursor"] == 500 and body["total"] == 501
            assert (
                body["integrity"]["valid"]
                and body["integrity"]["checked_events"] == 501
            )
            last = await api.get(
                f"/api/v1/events/lots/{lot.id}/history?after=500&page_size=500"
            )
            assert [e["sequence_number"] for e in last.json()["events"]] == [501]
            assert last.json()["next_cursor"] is None
            assert (
                await api.get(f"/api/v1/events/lots/{lot.id}/history?page_size=501")
            ).status_code == 422
    finally:
        integrity._cleanup_lot_records(admin_session, farm, product, [lot.id])


@pytest.mark.asyncio
async def test_detail_shows_root_farm_after_two_generations(lineage, admin_session):
    owner, products, _ = lineage
    farm = Farm(
        organization_id=owner.organization_id,
        name="Vườn xoài Cát Chu",
        area_ha=Decimal("1"),
        latitude=Decimal("10"),
        longitude=Decimal("106"),
    )
    admin_session.add(farm)
    admin_session.commit()
    root = add_lot(admin_session, owner, products[0])
    root.farm_id = farm.id
    admin_session.commit()
    async with client() as api:
        await login(api, owner)
        child = (
            await api.post(f"/api/v1/lots/{root.id}/split", json=split_body("20"))
        ).json()["children"][0]
        grandchild = (
            await api.post(f"/api/v1/lots/{child['id']}/split", json=split_body("10"))
        ).json()["children"][0]
        response = await api.get(f"/api/v1/lots/{grandchild['id']}")
        assert response.status_code == 200, response.text
        assert [f["name"] for f in response.json()["root_farms"]] == [farm.name]


@pytest.mark.performance
def test_five_thousand_lots_filtered_cursor_page_under_300ms(
    admin_session, identity_factory
):
    owner = identity_factory()
    farm, product, _, principal = integrity._create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    ids = [uuid4() for _ in range(5000)]
    try:
        admin_session.execute(
            Lot.__table__.insert(),
            [
                {
                    "id": id,
                    "organization_id": owner.organization_id,
                    "current_holder_organization_id": owner.organization_id,
                    "farm_id": farm.id,
                    "product_id": product.id,
                    "name": "Xoài Cát Chu",
                    "lot_code": f"B{index:07d}",
                    "quantity": Decimal("10"),
                    "remaining_quantity": Decimal("10"),
                    "status": "active",
                    "harvested_on": date.today(),
                }
                for index, id in enumerate(ids)
            ],
        )
        admin_session.commit()
        with SessionLocal() as db:
            set_db_context(db, session_token_hash=owner.session_token_hash)
            captured = []
            connection = db.connection()

            def capture(conn, cur, statement, parameters, context, many):
                captured.append((statement, parameters))

            event.listen(connection, "before_cursor_execute", capture)
            started = perf_counter()
            page = lot_service.list_lots(
                db,
                principal,
                query="b",
                product_id=product.id,
                page_size=20,
                cursor=None,
            )
            elapsed = perf_counter() - started
            event.remove(connection, "before_cursor_execute", capture)
            assert len(page["items"]) == 20 and page["next_cursor"]
            if elapsed >= 0.3:
                statement, parameters = captured[0]
                plan = connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters
                ).scalar()[0]["Plan"]

                def summarize(node):
                    print(
                        {
                            k: node.get(k)
                            for k in (
                                "Node Type",
                                "Relation Name",
                                "Actual Total Time",
                                "Actual Loops",
                                "Actual Rows",
                            )
                        }
                    )
                    for child in node.get("Plans", []):
                        summarize(child)

                summarize(plan)
            assert elapsed < 0.3
            print(f"5000 lots, filtered 20-row page: {elapsed * 1000:.1f}ms")
            following = lot_service.list_lots(
                db,
                principal,
                query="B",
                product_id=product.id,
                page_size=20,
                cursor=page["next_cursor"],
            )
            assert not {r.id for r in page["items"]}.intersection(
                r.id for r in following["items"]
            )
    finally:
        admin_session.execute(delete(Lot).where(Lot.id.in_(ids)))
        admin_session.commit()
        # The fixture also contains one genesis lot/event.
        seed_lot = admin_session.query(Lot).filter(Lot.farm_id == farm.id).one()
        integrity._cleanup_lot_records(admin_session, farm, product, [seed_lot.id])
