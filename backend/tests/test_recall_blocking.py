"""S-38 / N3-53: block handover, split, and merge for lots under recall.

Scenarios:
- Open recall order blocks all three operations and returns the recall code.
- Completed recall order with incident_flag=True keeps blocking.
- Completed recall order with incident_flag=False allows operations.
- Lots not in any recall order are unaffected.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.handover import Handover
from app.models.identity import Organization, User
from app.models.lot import Lot
from app.models.product import Product
from app.models.recall import RecallOrder, RecallOrderLot
from app.schemas.handover import HandoverCreate
from app.schemas.lineage import LotMerge, LotSplit, MergeParent, SplitChild
from app.schemas.recall import RecallOrderCreate
from app.services import handover_service, lineage_service, recall_service


def _make_principal(org_id: UUID, user_id: UUID) -> Principal:
    return Principal(
        user_id=user_id,
        email="test@example.com",
        full_name="Test User",
        organization_id=org_id,
        organization_name="Test Org",
        organization_type="farm",
        role="grower",
    )


def _make_lot(
    db: Session, org_id: UUID, *, name: str = "Test Lot", quantity: str = "100"
) -> Lot:
    product = Product(name=f"Product-{uuid4().hex[:6]}", unit="kg", is_active=True)
    db.add(product)
    db.flush()
    lot = Lot(
        organization_id=org_id,
        current_holder_organization_id=org_id,
        name=name,
        lot_code=f"L{uuid4().hex[:10].upper()}",
        product_id=product.id,
        harvested_on=date(2026, 10, 1),
        quantity=Decimal(quantity),
        remaining_quantity=Decimal(quantity),
        status="active",
    )
    db.add(lot)
    db.flush()
    return lot


def _make_recall(
    db: Session,
    org_id: UUID,
    user_id: UUID,
    lot: Lot,
    *,
    code: str = "RC-001",
    status: str = "open",
    incident_flag: bool = True,
) -> RecallOrder:
    order = RecallOrder(
        organization_id=org_id,
        code=code,
        status=status,
        created_by_user_id=user_id,
    )
    db.add(order)
    db.flush()
    db.add(
        RecallOrderLot(
            recall_order_id=order.id,
            organization_id=org_id,
            lot_id=lot.id,
            incident_flag=incident_flag,
        )
    )
    db.flush()
    return order


def _make_org_and_user(db: Session) -> tuple[Organization, User]:
    org = Organization(
        name=f"Recall-Org-{uuid4().hex[:6]}",
        organization_type="farm",
        is_active=True,
    )
    db.add(org)
    db.flush()
    user = User(
        organization_id=org.id,
        role_code="grower",
        email=f"{uuid4().hex}@example.com",
        full_name="Recall Tester",
        password_hash="x",
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return org, user


def test_open_recall_blocks_handover(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    _make_recall(admin_session, org.id, user.id, lot, code="RC-BLOCK-1")
    admin_session.commit()

    principal = _make_principal(org.id, user.id)
    payload = HandoverCreate(lot_id=lot.id, to_organization_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        handover_service.create_handover(admin_session, principal, payload)
    assert exc_info.value.status_code == 409
    assert "RC-BLOCK-1" in exc_info.value.detail


def test_open_recall_blocks_split(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    _make_recall(admin_session, org.id, user.id, lot, code="RC-BLOCK-2")
    admin_session.commit()

    principal = _make_principal(org.id, user.id)
    payload = LotSplit(
        children=[SplitChild(name="Child A", quantity=Decimal("30"))]
    )
    with pytest.raises(HTTPException) as exc_info:
        lineage_service.split_lot(admin_session, principal, lot.id, payload)
    assert exc_info.value.status_code == 409
    assert "RC-BLOCK-2" in exc_info.value.detail


def test_open_recall_blocks_merge(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot_a = _make_lot(admin_session, org.id, name="Lot A")
    lot_b = _make_lot(admin_session, org.id, name="Lot B")
    _make_recall(admin_session, org.id, user.id, lot_a, code="RC-BLOCK-3")
    admin_session.commit()

    principal = _make_principal(org.id, user.id)
    payload = LotMerge(
        name="Merged",
        parents=[
            MergeParent(lot_id=lot_a.id, quantity=Decimal("10")),
            MergeParent(lot_id=lot_b.id, quantity=Decimal("10")),
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        lineage_service.merge_lots(admin_session, principal, payload)
    assert exc_info.value.status_code == 409
    assert "RC-BLOCK-3" in exc_info.value.detail


def test_completed_recall_with_incident_flag_blocks(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    _make_recall(
        admin_session,
        org.id,
        user.id,
        lot,
        code="RC-COMPLETED-1",
        status="completed",
        incident_flag=True,
    )
    admin_session.commit()

    principal = _make_principal(org.id, user.id)
    payload = HandoverCreate(lot_id=lot.id, to_organization_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        handover_service.create_handover(admin_session, principal, payload)
    assert exc_info.value.status_code == 409
    assert "RC-COMPLETED-1" in exc_info.value.detail


def test_completed_recall_without_incident_flag_allows(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    _make_recall(
        admin_session,
        org.id,
        user.id,
        lot,
        code="RC-COMPLETED-2",
        status="completed",
        incident_flag=False,
    )
    admin_session.commit()

    blocking = recall_service.get_blocking_recall(admin_session, lot.id)
    assert blocking is None


def test_lot_not_in_recall_is_unaffected(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    admin_session.commit()

    blocking = recall_service.get_blocking_recall(admin_session, lot.id)
    assert blocking is None


def test_create_recall_order_generates_code_and_blocks(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    admin_session.commit()

    principal = _make_principal(org.id, user.id)
    payload = RecallOrderCreate(code="RC-NEW-1", lot_ids=[lot.id])
    order = recall_service.create_recall_order(admin_session, principal, payload)
    assert order.code == "RC-NEW-1"
    assert order.status == "open"

    blocking = recall_service.get_blocking_recall(admin_session, lot.id)
    assert blocking is not None
    assert blocking.code == "RC-NEW-1"


def test_complete_recall_then_clear_flag_allows_operations(
    admin_session: Session,
):
    org, user = _make_org_and_user(admin_session)
    lot = _make_lot(admin_session, org.id)
    order = _make_recall(
        admin_session,
        org.id,
        user.id,
        lot,
        code="RC-LIFECYCLE",
        status="completed",
        incident_flag=True,
    )
    admin_session.commit()

    principal = _make_principal(org.id, user.id)

    # Still blocked while incident flag is True.
    with pytest.raises(HTTPException):
        recall_service.raise_if_recall_blocked(admin_session, lot.id)

    # Clear the flag.
    recall_service.update_incident_flag(
        admin_session, principal, order.id, lot.id, False
    )

    # Now allowed.
    recall_service.raise_if_recall_blocked(admin_session, lot.id)
