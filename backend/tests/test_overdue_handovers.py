"""Overdue markers preserve pending custody and late immutable acknowledgements."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import settings
from app.core.database import SessionLocal, set_db_context
from app.models.event import Event
from app.models.handover import Handover
from app.models.lot import Lot
from app.services import handover_service
from app.services.event_service import verify_event_chain
from tests import test_sprint3_lineage as fixtures
from tests.lineage_helpers import add_lot, client, login

lineage = fixtures.lineage
lineage_products = fixtures.lineage_products


def test_runtime_maintenance_marks_only_expired_pending(overdue_case, admin_session):
    from app.jobs.scheduler import mark_overdue

    _, _, create = overdue_case
    old = create(created_at=datetime.now(UTC) - timedelta(hours=49))
    fresh = create(created_at=datetime.now(UTC) - timedelta(hours=1))
    resolved = create(
        created_at=datetime.now(UTC) - timedelta(hours=72), status="rejected"
    )
    assert mark_overdue() >= 1
    assert mark_overdue() == 0
    admin_session.expire_all()
    assert old.overdue_at is not None and old.status == "pending"
    assert fresh.overdue_at is None
    assert resolved.overdue_at is None
    with SessionLocal() as runtime:
        with pytest.raises(DBAPIError):
            runtime.execute(text("SELECT public.app_mark_overdue_handovers(0)"))
        runtime.rollback()
        assert not runtime.scalar(
            text(
                "SELECT has_function_privilege('public','public.app_mark_overdue_handovers(integer)','EXECUTE')"
            )
        )


@pytest.fixture
def overdue_case(lineage, admin_session):
    recipient, products, identities = lineage
    sender = identities()

    def create(*, created_at, status="pending"):
        lot = add_lot(admin_session, sender, products[0], status="pending_handover")
        handover = Handover(
            lot_id=lot.id,
            from_organization_id=sender.organization_id,
            to_organization_id=recipient.organization_id,
            created_by_user_id=sender.user_id,
            created_at=created_at,
            status=status,
        )
        admin_session.add(handover)
        admin_session.commit()
        return handover

    return sender, recipient, create


def test_scan_strict_boundary_idempotency_and_batches(overdue_case, admin_session):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    _, _, create = overdue_case
    now = datetime.now(UTC)
    boundary = create(created_at=now - timedelta(hours=48))
    before = create(created_at=now - timedelta(hours=48) + timedelta(microseconds=1))
    overdue = [
        create(created_at=now - timedelta(hours=48, microseconds=offset))
        for offset in (1, 2, 3)
    ]
    resolved = create(created_at=now - timedelta(hours=72), status="rejected")

    assert scan_overdue_handovers(admin_session, now=now, batch_size=2) == 3
    assert scan_overdue_handovers(admin_session, now=now, batch_size=2) == 0
    admin_session.expire_all()
    for handover in overdue:
        assert handover.overdue_at == now
        assert handover.status == "pending"
        assert admin_session.get(Lot, handover.lot_id).status == "pending_handover"
    assert boundary.overdue_at is None
    assert before.overdue_at is None
    assert resolved.overdue_at is None
    assert (
        list(
            admin_session.scalars(
                select(Event).where(
                    Event.lot_id.in_(
                        [row.lot_id for row in [boundary, before, resolved, *overdue]]
                    )
                )
            )
        )
        == []
    )


def test_configurable_scan_threshold(overdue_case, admin_session, monkeypatch):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    _, _, create = overdue_case
    now = datetime.now(UTC)
    handover = create(created_at=now - timedelta(hours=3))
    monkeypatch.setattr(settings, "HANDOVER_OVERDUE_HOURS", 2)
    assert scan_overdue_handovers(admin_session, now=now) == 1
    admin_session.refresh(handover)
    assert handover.overdue_at == now


@pytest.mark.asyncio
async def test_both_parties_receive_persisted_marker(overdue_case, admin_session):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    sender, recipient, create = overdue_case
    now = datetime.now(UTC)
    handover = create(created_at=now - timedelta(hours=49))
    assert scan_overdue_handovers(admin_session, now=now) == 1
    for identity, direction in ((sender, "outgoing"), (recipient, "incoming")):
        async with client() as api:
            await login(api, identity)
            response = await api.get(f"/api/v1/handovers/{direction}")
            assert response.status_code == 200, response.text
            row = next(row for row in response.json() if row["id"] == str(handover.id))
            assert datetime.fromisoformat(row["overdue_at"]) == now
            assert row["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("scanned", [False, True])
async def test_late_accept_logs_acknowledgement_even_if_scan_missed(
    overdue_case, admin_session, scanned
):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    _, recipient, create = overdue_case
    handover = create(created_at=datetime.now(UTC) - timedelta(hours=49))
    if scanned:
        assert scan_overdue_handovers(admin_session) == 1
    async with client() as api:
        await login(api, recipient)
        response = await api.post(f"/api/v1/handovers/{handover.id}/accept")
        assert response.status_code == 200, response.text
        repeated = await api.post(f"/api/v1/handovers/{handover.id}/accept")
        assert repeated.status_code == 409
    admin_session.expire_all()
    assert handover.status == "accepted"
    assert handover.overdue_at is not None
    lot = admin_session.get(Lot, handover.lot_id)
    assert lot.current_holder_organization_id == recipient.organization_id
    assert lot.status == "active"
    events = list(
        admin_session.scalars(select(Event).where(Event.lot_id == lot.id)).all()
    )
    assert len(events) == 1
    assert events[0].payload["late_acknowledgement"] is True
    assert (
        datetime.fromisoformat(events[0].payload["overdue_at"]) == handover.overdue_at
    )
    assert verify_event_chain(events)["valid"] is True


def test_late_accept_failure_rolls_back_marker_custody_and_event(
    overdue_case, admin_session, monkeypatch
):
    sender, recipient, create = overdue_case
    handover = create(created_at=datetime.now(UTC) - timedelta(hours=49))
    handover_id, lot_id = handover.id, handover.lot_id
    original = handover_service.event_service.append_event

    def fail_after_event(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated late acknowledgement failure")

    monkeypatch.setattr(
        handover_service.event_service, "append_event", fail_after_event
    )
    principal = Principal(
        user_id=recipient.user_id,
        email=recipient.email,
        full_name="Test recipient",
        organization_id=recipient.organization_id,
        organization_name="Recipient",
        organization_type="cooperative",
        role="cooperative",
    )
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=recipient.session_token_hash)
        with pytest.raises(RuntimeError, match="simulated late"):
            handover_service.accept_handover(db, principal, handover_id)
    admin_session.expire_all()
    assert handover.status == "pending"
    assert handover.overdue_at is None
    lot = admin_session.get(Lot, lot_id)
    assert lot.current_holder_organization_id == sender.organization_id
    assert lot.status == "pending_handover"
    assert (
        list(admin_session.scalars(select(Event).where(Event.lot_id == lot_id))) == []
    )


def test_scan_skips_locked_rows_until_next_scan(
    overdue_case, admin_session, admin_engine
):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    _, _, create = overdue_case
    now = datetime.now(UTC)
    locked = create(created_at=now - timedelta(hours=49))
    unlocked = create(created_at=now - timedelta(hours=50))
    with Session(admin_engine) as locker, Session(admin_engine) as scanner:
        locker.scalar(
            select(Handover).where(Handover.id == locked.id).with_for_update()
        )
        assert scan_overdue_handovers(scanner, now=now, batch_size=1) == 1
        admin_session.expire_all()
        assert locked.overdue_at is None
        assert unlocked.overdue_at == now
        locker.rollback()
        assert scan_overdue_handovers(scanner, now=now, batch_size=1) == 1
    admin_session.refresh(locked)
    assert locked.overdue_at == now


@pytest.mark.parametrize("offset,late", [(-1, False), (0, False), (1, True)])
def test_accept_exact_threshold_boundary(
    overdue_case, admin_session, monkeypatch, offset, late
):
    _, recipient, create = overdue_case
    now = datetime.now(UTC)
    handover = create(created_at=now - timedelta(hours=48, microseconds=offset))

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(handover_service, "datetime", FrozenDatetime)
    principal = Principal(
        user_id=recipient.user_id,
        email=recipient.email,
        full_name="Test recipient",
        organization_id=recipient.organization_id,
        organization_name="Recipient",
        organization_type="cooperative",
        role="cooperative",
    )
    with SessionLocal() as db:
        set_db_context(db, session_token_hash=recipient.session_token_hash)
        handover_service.accept_handover(db, principal, handover.id)
    admin_session.expire_all()
    event = admin_session.scalar(select(Event).where(Event.lot_id == handover.lot_id))
    assert event.payload["late_acknowledgement"] is late
    assert handover.overdue_at == (now if late else None)


def test_scan_failure_rolls_back_uncommitted_batch(
    overdue_case, admin_session, monkeypatch
):
    from app.jobs.overdue_handovers import scan_overdue_handovers

    _, _, create = overdue_case
    handover = create(created_at=datetime.now(UTC) - timedelta(hours=49))

    def fail_commit():
        raise RuntimeError("simulated scan commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(admin_session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated scan"):
            scan_overdue_handovers(admin_session)
    admin_session.refresh(handover)
    assert handover.overdue_at is None
    assert handover.status == "pending"
