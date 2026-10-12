from datetime import date
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.crypto import GENESIS_PREV_HASH, compute_event_hash
from app.core.database import engine as application_engine
from app.main import app
from app.models.event import Event
from app.models.farm import Farm
from app.models.identity import Organization
from app.models.integrity_check import IntegrityCheck
from app.models.lot import Lot
from app.models.product import Product
from app.services import event_service
from app.services.event_service import verify_event_chain
from tests.conftest import IdentityFixture


def _event(sequence_number: int, previous_hash: str, lot_id, organization_id):
    payload = {"value": sequence_number}
    content = {
        "event_type": "test",
        "lot_id": str(lot_id),
        "organization_id": str(organization_id),
        "payload": payload,
        "sequence_number": sequence_number,
    }
    return SimpleNamespace(
        sequence_number=sequence_number,
        prev_hash=previous_hash,
        event_hash=compute_event_hash(previous_hash, content),
        event_type="test",
        lot_id=lot_id,
        organization_id=organization_id,
        payload=payload,
    )


def _valid_chain(count: int = 3):
    lot_id = uuid4()
    organization_id = uuid4()
    events = []
    previous_hash = GENESIS_PREV_HASH
    for sequence in range(1, count + 1):
        event = _event(sequence, previous_hash, lot_id, organization_id)
        events.append(event)
        previous_hash = event.event_hash
    return events


def test_streamed_verification_keeps_downstream_warnings():
    events = _valid_chain(501)
    events[499].payload["value"] = -1
    result = verify_event_chain(iter(events))
    assert result["checked_events"] == 501
    assert result["first_invalid_sequence"] == 500
    assert result["issues"][-1].sequence_number == 501
    assert result["issues"][-1].kind == "downstream_unverified"


def _create_lot_records(db: Session, identity: IdentityFixture, suffix: str):
    farm = Farm(
        organization_id=identity.organization_id,
        name=f"integrity-farm-{suffix}",
        area_ha=Decimal("1.0000"),
        latitude=Decimal("10.000000"),
        longitude=Decimal("106.000000"),
    )
    product = Product(name=f"integrity-product-{suffix}", unit="kg")
    db.add_all([farm, product])
    db.flush()
    lot = Lot(
        organization_id=identity.organization_id,
        current_holder_organization_id=identity.organization_id,
        farm_id=farm.id,
        name="Integrity test lot",
        lot_code=f"V{suffix[:8].upper()}",
        product_id=product.id,
        harvested_on=date.today(),
        quantity=Decimal("3.000"),
        remaining_quantity=Decimal("3.000"),
        status="active",
    )
    db.add(lot)
    db.commit()
    principal = Principal(
        user_id=identity.user_id,
        email=identity.email,
        full_name="Integrity test user",
        organization_id=identity.organization_id,
        organization_name="Integrity test organization",
        organization_type="farm",
        role="grower",
    )
    return farm, product, lot, principal


def _append_chain(db: Session, principal: Principal, lot_id, count: int) -> None:
    for sequence in range(1, count + 1):
        event_service.append_event(
            db,
            principal,
            lot_id,
            event_type="integrity_test",
            payload={"value": sequence},
        )
    db.commit()


def _cleanup_lot_records(db: Session, farm: Farm, product: Product, lot_ids) -> None:
    if lot_ids:
        with db.begin_nested():
            db.execute(text("ALTER TABLE events DISABLE TRIGGER USER"))
            db.execute(text("ALTER TABLE integrity_checks DISABLE TRIGGER USER"))
            db.execute(delete(IntegrityCheck).where(IntegrityCheck.lot_id.in_(lot_ids)))
            db.execute(delete(Event).where(Event.lot_id.in_(lot_ids)))
            db.execute(text("ALTER TABLE integrity_checks ENABLE TRIGGER USER"))
            db.execute(text("ALTER TABLE events ENABLE TRIGGER USER"))
        db.execute(delete(Lot).where(Lot.id.in_(lot_ids)))
    db.execute(delete(Farm).where(Farm.id == farm.id))
    db.execute(delete(Product).where(Product.id == product.id))
    db.commit()


def test_single_event_chain_is_valid():
    result = verify_event_chain(_valid_chain(1))

    assert result["valid"] is True
    assert result["checked_events"] == 1
    assert result["issues"] == []


def test_one_thousand_events_verify_under_one_second():
    events = _valid_chain(1_000)

    started = perf_counter()
    result = verify_event_chain(events)
    elapsed = perf_counter() - started

    assert result["valid"] is True
    assert result["checked_events"] == 1_000
    assert elapsed < 1.0


def test_integrity_check_is_persisted_with_timestamp(
    admin_session: Session, identity_factory
):
    owner = identity_factory(role="inspector", organization_type="inspection")
    farm, product, lot, principal = _create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    try:
        _append_chain(admin_session, principal, lot.id, 1)

        principal = Principal(
            user_id=owner.user_id,
            email=owner.email,
            full_name="Integrity test inspector",
            organization_id=owner.organization_id,
            organization_name="Integrity test organization",
            organization_type="inspection",
            role="inspector",
        )
        report = event_service.record_integrity_check(admin_session, principal, lot.id)

        assert report["checked_at"] is not None
        saved_check = admin_session.scalar(
            select(IntegrityCheck).where(IntegrityCheck.id == report["id"])
        )
        assert saved_check is not None
        assert saved_check.valid is True
        assert saved_check.checked_events == 1
        assert saved_check.checked_at == report["checked_at"]
        history = event_service.get_integrity_check_history(
            admin_session, principal, lot.id
        )
        assert len(history) == 1
        assert history[0].id == report["id"]
    finally:
        _cleanup_lot_records(admin_session, farm, product, [lot.id])


@pytest.mark.asyncio
async def test_integrity_check_endpoint_returns_saved_audit_history(
    admin_session: Session, identity_factory
):
    owner = identity_factory(role="inspector", organization_type="inspection")
    farm, product, lot, principal = _create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    _append_chain(admin_session, principal, lot.id, 2)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": owner.email, "password": owner.password},
            )
            assert login.status_code == 200, login.text

            response = await client.post(
                f"/api/v1/events/lots/{lot.id}/integrity-checks"
            )
            history = await client.get(f"/api/v1/events/lots/{lot.id}/integrity-checks")

        assert response.status_code == 201, response.text
        assert response.json()["valid"] is True
        assert response.json()["checked_events"] == 2
        assert response.json()["checked_at"]
        assert history.status_code == 200, history.text
        assert len(history.json()) == 1
        assert history.json()[0]["id"] == response.json()["id"]
    finally:
        _cleanup_lot_records(admin_session, farm, product, [lot.id])


def test_tampered_event_marks_it_and_all_later_events_suspect():
    events = _valid_chain()
    events[1].payload["value"] = 99

    result = verify_event_chain(events)

    assert result["valid"] is False
    assert result["first_invalid_sequence"] == 2
    assert [(issue.sequence_number, issue.kind) for issue in result["issues"]] == [
        (2, "content_hash_mismatch"),
        (3, "downstream_unverified"),
    ]


def test_deleted_middle_event_reports_gap_and_later_event_as_suspect():
    events = _valid_chain()

    result = verify_event_chain([events[0], events[2]])

    assert result["valid"] is False
    assert result["first_invalid_sequence"] == 2
    assert [(issue.sequence_number, issue.kind) for issue in result["issues"]] == [
        (2, "missing_event"),
        (3, "downstream_unverified"),
    ]


def test_sql_tamper_delete_and_intact_cases_are_detected(
    admin_session: Session, identity_factory
):
    owner = identity_factory()
    suffix = uuid4().hex[:8]
    farm, product, intact_lot, principal = _create_lot_records(
        admin_session, owner, suffix
    )
    lots = [intact_lot]
    try:
        _append_chain(admin_session, principal, intact_lot.id, 3)
        intact_events = event_service.list_events_for_lot(
            admin_session, principal, intact_lot.id
        )
        assert verify_event_chain(intact_events)["valid"] is True

        tampered_lot = Lot(
            organization_id=owner.organization_id,
            current_holder_organization_id=owner.organization_id,
            farm_id=farm.id,
            name="SQL tamper test lot",
            lot_code=f"T{uuid4().hex[:8].upper()}",
            product_id=product.id,
            harvested_on=date.today(),
            quantity=Decimal("3.000"),
            remaining_quantity=Decimal("3.000"),
            status="active",
        )
        deleted_lot = Lot(
            organization_id=owner.organization_id,
            current_holder_organization_id=owner.organization_id,
            farm_id=farm.id,
            name="SQL delete test lot",
            lot_code=f"D{uuid4().hex[:8].upper()}",
            product_id=product.id,
            harvested_on=date.today(),
            quantity=Decimal("3.000"),
            remaining_quantity=Decimal("3.000"),
            status="active",
        )
        admin_session.add_all([tampered_lot, deleted_lot])
        admin_session.commit()
        lots.extend([tampered_lot, deleted_lot])
        _append_chain(admin_session, principal, tampered_lot.id, 3)
        _append_chain(admin_session, principal, deleted_lot.id, 3)

        with admin_session.begin_nested():
            admin_session.execute(text("ALTER TABLE events DISABLE TRIGGER USER"))
            admin_session.execute(
                text(
                    "UPDATE events SET payload = CAST(:payload AS jsonb) "
                    "WHERE lot_id = :lot_id AND sequence_number = 2"
                ),
                {"payload": '{"value":999}', "lot_id": tampered_lot.id},
            )
            admin_session.execute(text("ALTER TABLE events ENABLE TRIGGER USER"))
        admin_session.commit()
        admin_session.expire_all()
        tampered_result = verify_event_chain(
            event_service.list_events_for_lot(admin_session, principal, tampered_lot.id)
        )
        assert tampered_result["valid"] is False
        assert tampered_result["first_invalid_sequence"] == 2

        with admin_session.begin_nested():
            admin_session.execute(text("ALTER TABLE events DISABLE TRIGGER USER"))
            admin_session.execute(
                delete(Event).where(
                    Event.lot_id == deleted_lot.id,
                    Event.sequence_number == 2,
                )
            )
            admin_session.execute(text("ALTER TABLE events ENABLE TRIGGER USER"))
        admin_session.commit()
        admin_session.expire_all()
        deleted_result = verify_event_chain(
            event_service.list_events_for_lot(admin_session, principal, deleted_lot.id)
        )
        assert deleted_result["valid"] is False
        assert deleted_result["first_invalid_sequence"] == 2
        assert deleted_result["issues"][0].kind == "missing_event"
    finally:
        _cleanup_lot_records(admin_session, farm, product, [lot.id for lot in lots])


@pytest.mark.asyncio
async def test_two_hundred_event_history_is_fast_and_does_not_query_per_event(
    admin_session: Session, identity_factory
):
    owner = identity_factory()
    farm, product, lot, principal = _create_lot_records(
        admin_session, owner, uuid4().hex[:8]
    )
    expected_organization_name = admin_session.scalar(
        select(Organization.name).where(Organization.id == owner.organization_id)
    )
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, _params, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    _append_chain(admin_session, principal, lot.id, 200)
    listener_registered = False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": owner.email, "password": owner.password},
            )
            assert login.status_code == 200, login.text
            sqlalchemy_event.listen(
                application_engine, "before_cursor_execute", count_selects
            )
            listener_registered = True
            started = perf_counter()
            response = await client.get(f"/api/v1/events/lots/{lot.id}/history")
            elapsed = perf_counter() - started

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["events"]) == 200
        assert all(
            event["organization_name"] == expected_organization_name
            for event in body["events"]
        )
        assert body["integrity"]["valid"] is True
        assert elapsed < 2.0
        assert len(statements) <= 10
    finally:
        if listener_registered:
            sqlalchemy_event.remove(
                application_engine, "before_cursor_execute", count_selects
            )
        _cleanup_lot_records(admin_session, farm, product, [lot.id])
