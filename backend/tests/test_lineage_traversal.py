from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from app.core.auth import Principal
from app.core.database import SessionLocal, engine, set_db_context
from app.models.lot import Lot
from app.models.lot_relation import LotRelation
from app.services.traversal_service import get_detail, get_lineage
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login, split_body

lineage = fixtures.lineage
lineage_products = fixtures.lineage_products


@pytest.mark.asyncio
async def test_trace_merge_has_all_roots_and_descendants(lineage, admin_session):
    owner, products, _ = lineage
    roots = [add_lot(admin_session, owner, products[0]) for _ in range(2)]
    async with client() as api:
        await login(api, owner)
        split = await api.post(
            f"/api/v1/lots/{roots[0].id}/split", json=split_body("10", "10")
        )
        first_child = split.json()["children"][0]
        merged = await api.post(
            "/api/v1/lots/merge",
            json={
                "name": "Mixed",
                "parents": [
                    {"lot_id": first_child["id"], "quantity": "10"},
                    {"lot_id": str(roots[1].id), "quantity": "20"},
                ],
            },
        )
        trace = await api.get(
            f"/api/v1/lots/{merged.json()['id']}/lineage?direction=ancestors"
        )
        assert trace.status_code == 200, trace.text
        assert set(trace.json()["roots"]) == {str(root.id) for root in roots}
        assert len(trace.json()["nodes"]) == 4
        downstream = await api.get(
            f"/api/v1/lots/{roots[0].id}/lineage?direction=descendants"
        )
        assert downstream.status_code == 200
        assert {node["id"] for node in downstream.json()["nodes"]} == {
            str(roots[0].id),
            merged.json()["id"],
            *(item["id"] for item in split.json()["children"]),
        }
        # Elevated injected corruption still must terminate and report a cycle.
        admin_session.execute(
            text(
                "INSERT INTO lot_relations(id, organization_id, parent_lot_id, child_lot_id, quantity, operation) VALUES (gen_random_uuid(), :org, :parent, :child, 1, 'split')"
            ),
            {
                "org": owner.organization_id,
                "parent": UUID(merged.json()["id"]),
                "child": roots[0].id,
            },
        )
        admin_session.commit()
        cycle = await api.get(
            f"/api/v1/lots/{roots[0].id}/lineage?direction=descendants"
        )
        assert cycle.status_code == 409, cycle.text
        cycle_codes = {
            roots[0].lot_code,
            first_child["lot_code"],
            merged.json()["lot_code"],
        }
        assert any(code in cycle.json()["detail"] for code in cycle_codes)


@pytest.mark.asyncio
async def test_receiver_reads_sources_but_old_holder_history_is_cut_off(
    lineage, admin_session
):
    receiver, products, identities = lineage
    grower = identities()
    root = add_lot(admin_session, grower, products[0])
    unrelated = add_lot(admin_session, grower, products[0])
    async with client() as source_api, client() as receiving_api:
        await login(source_api, grower)
        await login(receiving_api, receiver)
        transfer = await source_api.post(
            "/api/v1/handovers/",
            json={
                "lot_id": str(root.id),
                "to_organization_id": str(receiver.organization_id),
            },
        )
        await receiving_api.post(f"/api/v1/handovers/{transfer.json()['id']}/accept")
        split = await receiving_api.post(
            f"/api/v1/lots/{root.id}/split", json=split_body("10")
        )
        trace = await receiving_api.get(
            f"/api/v1/lots/{split.json()['children'][0]['id']}/lineage?direction=ancestors"
        )
        assert trace.status_code == 200, trace.text
        assert trace.json()["roots"] == [str(root.id)]
        assert (
            await receiving_api.get(f"/api/v1/lots/{unrelated.id}")
        ).status_code == 403
        former = await source_api.get(f"/api/v1/events/lots/{root.id}/history")
        assert former.status_code == 200, former.text
        assert [event["event_type"] for event in former.json()["events"]] == [
            "handover_pending",
            "handover_accepted",
        ]
        assert former.json()["integrity"]["valid"]
        forbidden_write = await source_api.post(
            "/api/v1/events/", json={"lot_id": str(root.id), "event_type": "forged"}
        )
        assert forbidden_write.status_code == 403
        third = identities(role="distributor", organization_type="distribution")
        child_id = split.json()["children"][0]["id"]
        transfer_child = await receiving_api.post(
            "/api/v1/handovers/",
            json={"lot_id": child_id, "to_organization_id": str(third.organization_id)},
        )
        async with client() as third_api:
            await login(third_api, third)
            assert (
                await third_api.post(
                    f"/api/v1/handovers/{transfer_child.json()['id']}/accept"
                )
            ).status_code == 200
            third_trace = await third_api.get(f"/api/v1/lots/{child_id}/lineage")
            assert third_trace.status_code == 200, third_trace.text
            assert third_trace.json()["roots"] == [str(root.id)]
            assert third_trace.json()["root_farms"][0]["id"] == str(root.farm_id)
            assert (
                await third_api.get(f"/api/v1/lots/{unrelated.id}")
            ).status_code == 403
            fourth = identities(role="distributor", organization_type="distribution")
            next_handover = await third_api.post(
                "/api/v1/handovers/",
                json={
                    "lot_id": child_id,
                    "to_organization_id": str(fourth.organization_id),
                },
            )
            assert next_handover.status_code == 201
            async with client() as fourth_api:
                await login(fourth_api, fourth)
                assert (
                    await fourth_api.post(
                        f"/api/v1/handovers/{next_handover.json()['id']}/accept"
                    )
                ).status_code == 200
            later = await receiving_api.post(
                "/api/v1/events/",
                json={
                    "lot_id": str(root.id),
                    "event_type": "inspection",
                    "payload": {"note": "After former child's handover"},
                },
            )
            assert later.status_code == 201
            former_ancestor = await third_api.get(
                f"/api/v1/events/lots/{root.id}/history"
            )
            assert former_ancestor.status_code == 200, former_ancestor.text
            assert later.json()["id"] not in {
                item["id"] for item in former_ancestor.json()["events"]
            }
            historical_graph = await third_api.get(f"/api/v1/lots/{child_id}/lineage")
            assert historical_graph.status_code == 200, historical_graph.text
            assert all(
                node["historical_only"] for node in historical_graph.json()["nodes"]
            )
            assert all(
                node["remaining_quantity"] is None
                for node in historical_graph.json()["nodes"]
            )
        # The former custodian still knows the sources of its former child.
        historical_source = await receiving_api.get(
            f"/api/v1/events/lots/{root.id}/history"
        )
        assert historical_source.status_code == 200, historical_source.text
        assert historical_source.json()["integrity"]["valid"]


@pytest.mark.asyncio
@pytest.mark.performance
async def test_thousand_node_chain_is_complete_and_under_two_seconds(
    lineage, admin_session
):
    owner, products, _ = lineage
    root = add_lot(admin_session, owner, products[0])
    children = [
        Lot(
            id=uuid4(),
            organization_id=owner.organization_id,
            current_holder_organization_id=owner.organization_id,
            farm_id=None,
            name=f"Performance node {index}",
            lot_code=uuid4().hex[:12],
            product_id=products[0].id,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            status="active",
        )
        for index in range(999)
    ]
    admin_session.add_all(children)
    admin_session.flush()
    nodes = [root, *children]
    admin_session.add_all(
        [
            LotRelation(
                organization_id=owner.organization_id,
                parent_lot_id=parent.id,
                child_lot_id=child.id,
                quantity=Decimal("1"),
                operation="split",
            )
            for parent, child in zip(nodes, nodes[1:], strict=False)
        ]
    )
    admin_session.commit()
    async with client() as api:
        await login(api, owner)
        for target, direction in [(root, "descendants"), (children[-1], "ancestors")]:
            queries = []

            def before_query(conn, cur, sql, parameters, context, many):
                context.lineage_started = perf_counter()

            def after_query(conn, cur, sql, parameters, context, many, captured=queries):
                captured.append(
                    (perf_counter() - context.lineage_started, sql, parameters)
                )

            event.listen(engine, "before_cursor_execute", before_query)
            event.listen(engine, "after_cursor_execute", after_query)
            started = perf_counter()
            try:
                result = await api.get(
                    f"/api/v1/lots/{target.id}/lineage?direction={direction}"
                )
            finally:
                event.remove(engine, "before_cursor_execute", before_query)
                event.remove(engine, "after_cursor_execute", after_query)
            elapsed = perf_counter() - started
            print(f"1000 nodes {direction}: {elapsed:.3f}s")
            assert result.status_code == 200, result.text
            assert len(result.json()["nodes"]) == 1000
            assert len(result.json()["edges"]) == 999
            if elapsed >= 2:
                with SessionLocal() as db:
                    set_db_context(db, session_token_hash=owner.session_token_hash)
                    for duration, sql, parameters in queries:
                        print(f"Query {duration:.3f}s: {sql[:100]}")
                        if duration < 0.1 or (
                            "lot_relations" not in sql and "FROM lots" not in sql
                        ):
                            continue
                        report = (
                            db.connection()
                            .exec_driver_sql(
                                "EXPLAIN (ANALYZE, FORMAT JSON) " + sql, parameters
                            )
                            .scalar()[0]
                        )
                        print(
                            {key: report.get(key) for key in ("Execution Time", "JIT")}
                        )

                        def summarize(node):
                            print(
                                {
                                    key: node.get(key)
                                    for key in (
                                        "Node Type",
                                        "Relation Name",
                                        "Actual Total Time",
                                        "Actual Loops",
                                    )
                                }
                            )
                            for child in node.get("Plans", []):
                                summarize(child)

                        summarize(report["Plan"])
            assert elapsed < 2, f"{direction}: {elapsed:.3f}s"

    # Independently reproduce the nested-loop plan that repeats organization
    # authorization per node. Run after the API timings to avoid warming them.
    principal = Principal(
        owner.user_id,
        owner.email,
        "Test",
        owner.organization_id,
        "Test",
        "cooperative",
        "cooperative",
    )
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=owner.session_token_hash)
        connection = db.connection()
        connection.execute(text("SET LOCAL enable_hashjoin = off"))
        connection.execute(text("SET LOCAL enable_mergejoin = off"))
        connection.execute(text("SET LOCAL enable_material = off"))
        captured = []

        def capture(conn, cur, statement, parameters, context, many):
            captured.append((statement, parameters))

        event.listen(connection, "before_cursor_execute", capture)
        try:
            get_lineage(db, principal, root.id, "descendants")
        finally:
            event.remove(connection, "before_cursor_execute", capture)
        sql, parameters = captured[-1]
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + sql, parameters
        ).scalar()[0]["Plan"]

        def plan_nodes(node):
            yield node
            for child in node.get("Plans", []):
                yield from plan_nodes(child)

        organization_scans = [
            node
            for node in plan_nodes(plan)
            if node.get("Relation Name") == "organizations"
        ]
        assert organization_scans
        assert all(node["Actual Loops"] <= 1 for node in organization_scans)


def test_detail_uses_three_queries_with_runtime_role(lineage, admin_session):
    owner, products, _ = lineage
    root = add_lot(admin_session, owner, products[0])
    principal = Principal(
        owner.user_id,
        owner.email,
        "Test",
        owner.organization_id,
        "Test",
        "cooperative",
        "cooperative",
    )
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=owner.session_token_hash)
        statements = []
        connection = db.connection()

        def record_statement(
            connection, cursor, statement, parameters, context, executemany
        ):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", record_statement)
        try:
            result = get_detail(db, principal, root.id)
            assert result["id"] == root.id
            assert result["event_count"] == 0
            assert str(root.farm_id) in {farm["id"] for farm in result["root_farms"]}
            assert len(statements) == 3, statements
        finally:
            event.remove(connection, "before_cursor_execute", record_statement)
