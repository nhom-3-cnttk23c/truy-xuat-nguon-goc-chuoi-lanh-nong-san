"""Seed simulation of a 4-tier, 3-organization recall scenario with independent oracle (N3-54 / S-39)."""

import argparse
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import settings
from app.core.security import hash_password
from app.models.farm import Farm
from app.models.identity import Organization, User
from app.models.lot import Lot
from app.models.product import Product
from app.schemas.handover import HandoverCreate
from app.schemas.lineage import LotMerge, LotSplit
from app.schemas.location import LocationCreate, LotConsume, LotMove
from app.schemas.lot import LotCreate
from app.seed_lineage_demo import _lock_seed
from app.services import (
    handover_service,
    lineage_service,
    lot_lifecycle_service,
    lot_service,
)

RECALL_NAMESPACE = UUID("e5a7b8c9-1f2d-4e3a-9b8c-7d6e5f4a3b2c")
LABELS = (
    "R1",
    "R2",
    "R3",
    "A1",
    "A2",
    "B1",
    "B2",
    "C1",
    "C2",
    "M1",
    "M2",
    "M3",
    "D1",
    "D2",
    "E1",
    "E2",
    "F1",
    "F2",
)


def seed_recall_workflow(
    engine: Engine,
    principals: list[Principal],
    namespace: UUID = RECALL_NAMESPACE,
) -> dict[str, UUID]:
    """Execute realistic 4-tier 3-org recall workflow via domain services.

    Idempotent: Re-running on existing dataset verifies all 18 lots and returns existing IDs.
    """
    with (
        engine.begin() as connection,
        Session(bind=connection, join_transaction_mode="create_savepoint") as db,
    ):
        _lock_seed(db, namespace)
        product_id = uuid5(namespace, "product")
        existing = list(db.scalars(select(Lot).where(Lot.product_id == product_id)))
        if existing:
            labels = {lot.name.rsplit(" — ", 1)[-1]: lot.id for lot in existing}
            if len(existing) != 18 or set(labels) != set(LABELS):
                raise RuntimeError(
                    "Bộ mẫu thu hồi chưa đầy đủ hoặc không khớp; không ghi đè dữ liệu."
                )
            return {label: labels[label] for label in LABELS}

        if db.get(Product, product_id) is not None:
            raise RuntimeError(
                "Bộ mẫu thu hồi có danh mục nhưng thiếu lô; cần kiểm tra trước khi chạy lại."
            )

        product = Product(
            id=product_id,
            name="Cà chua cherry"
            if namespace == RECALL_NAMESPACE
            else f"Cà chua cherry (mẫu {namespace.hex[:8]})",
            description="Dữ liệu mẫu kịch bản thu hồi: đồ thị 4 tầng qua 3 tổ chức, có lô gộp đa nguồn và lô đã tiêu thụ.",
            unit="kg",
        )
        db.add(product)
        db.flush()

        lots: dict[str, Lot] = {}

        def label(lot: Lot, value: str) -> None:
            lot.name = f"Cà chua cherry — {value}"
            lots[value] = lot
            db.flush()

        def transfer(lot: Lot, sender: int, receiver: int) -> None:
            handover = handover_service.create_handover(
                db,
                principals[sender],
                HandoverCreate(
                    lot_id=lot.id,
                    to_organization_id=principals[receiver].organization_id,
                    note="Bàn giao lô phục vụ kịch bản thu hồi mẫu N3-54.",
                ),
            )
            handover_service.accept_handover(db, principals[receiver], handover["id"])

        def split(
            source: str, child_labels: list[str], amounts: list[str], actor: int
        ) -> None:
            result = lineage_service.split_lot(
                db,
                principals[actor],
                lots[source].id,
                LotSplit(
                    children=[
                        {"name": f"Cà chua cherry — {value}", "quantity": amount}
                        for value, amount in zip(child_labels, amounts, strict=True)
                    ]
                ),
            )
            for value, child_lot in zip(child_labels, result["children"], strict=True):
                lots[value] = child_lot

        # Tầng 1: Thu hoạch 3 lô tại Nông trại (Farm / Grower)
        for index, name in enumerate(
            (
                "Vườn cà chua số 1 (Thu hồi mẫu)",
                "Vườn cà chua số 2 (Thu hồi mẫu)",
                "Vườn cà chua số 3 (Thu hồi mẫu)",
            ),
            1,
        ):
            farm = Farm(
                id=uuid5(namespace, f"farm{index}"),
                organization_id=principals[0].organization_id,
                name=name,
                area_ha=Decimal("1"),
                latitude=Decimal("11.924850"),
                longitude=Decimal("108.497210"),
            )
            db.add(farm)
            db.flush()
            root = lot_service.create_harvest_lot(
                db,
                principals[0],
                LotCreate(
                    farm_id=farm.id,
                    product_id=product.id,
                    harvested_on=date(2026, 10, 1),
                    quantity=Decimal("100"),
                ),
            )
            label(root, f"R{index}")
            # Bàn giao từ Farm (0) sang Hợp tác xã (1)
            transfer(root, 0, 1)

        # Tầng 2: Hợp tác xã (1) tách 3 lô nguồn thành 6 lô thành phần
        for source, children in [
            ("R1", ["A1", "A2"]),
            ("R2", ["B1", "B2"]),
            ("R3", ["C1", "C2"]),
        ]:
            split(source, children, ["50", "50"], 1)

        # Tầng 3: Hợp tác xã (1) gộp chéo đa nguồn thành M1, M2, M3 và bàn giao sang Nhà phân phối (2)
        for value, parents in [
            ("M1", ["A1", "B1"]),  # Gộp từ R1 và R2
            ("M2", ["A2", "C1"]),  # Gộp từ R1 và R3
            ("M3", ["B2", "C2"]),  # Gộp từ R2 và R3
        ]:
            merged = lineage_service.merge_lots(
                db,
                principals[1],
                LotMerge(
                    name=f"Cà chua cherry — {value}",
                    parents=[
                        {"lot_id": lots[parent].id, "quantity": "50"}
                        for parent in parents
                    ],
                ),
            )
            lots[value] = merged
            # Bàn giao từ Hợp tác xã (1) sang Nhà phân phối (2)
            transfer(merged, 1, 2)

        # Tầng 4: Nhà phân phối (2) tách thành phẩm
        for source, children, amounts in [
            ("M1", ["D1", "D2"], ["40", "60"]),
            ("M2", ["E1", "E2"], ["50", "50"]),
            ("M3", ["F1", "F2"], ["30", "70"]),
        ]:
            split(source, children, amounts, 2)

        # Thiết lập vị trí kho và tiêu thụ lô tại Nhà phân phối (2)
        distribution_locations = lot_lifecycle_service.list_locations(db, principals[2])
        if distribution_locations:
            loc = distribution_locations[0]
        else:
            loc = lot_lifecycle_service.create_location(
                db,
                principals[2],
                LocationCreate(
                    name="Kho lạnh trung tâm (Thu hồi mẫu)",
                    address="Lô C1, Đường số 3, KCN Tân Bình, TP.HCM",
                ),
            )

        # Di chuyển lô D1 vào kho lạnh
        lot_lifecycle_service.move_lot(
            db,
            principals[2],
            lots["D1"].id,
            LotMove(location_id=loc.id, note="Lưu kho lạnh chuẩn bị phân phối"),
        )

        # Tiêu thụ lô D2 (60 kg) - chuyển status sang 'consumed', remaining_quantity = 0
        lot_lifecycle_service.consume_lot(
            db,
            principals[2],
            lots["D2"].id,
            LotConsume(note="Đã xuất bán lẻ ra hệ thống siêu thị tiêu thụ"),
        )

        # Tạo lệnh thu hồi mẫu trên một số lô tại Nhà phân phối
        from app.models.recall import RecallOrder, RecallOrderLot

        recall_order = RecallOrder(
            id=uuid5(namespace, "recall-order"),
            organization_id=principals[2].organization_id,
            code="RC-2026-001",
            status="open",
            note="Lệnh thu hồi mẫu S-38/N3-55.",
            created_by_user_id=principals[2].user_id,
        )
        db.add(recall_order)
        db.flush()

        for label in ("D1", "E1", "F1"):
            db.add(
                RecallOrderLot(
                    recall_order_id=recall_order.id,
                    organization_id=principals[2].organization_id,
                    lot_id=lots[label].id,
                    incident_flag=True,
                )
            )

        # Tạo lệnh thu hồi mẫu trên một số lô tại Nhà phân phối
        from app.models.recall import RecallOrder, RecallOrderLot

        recall_order = RecallOrder(
            id=uuid5(namespace, "recall-order"),
            organization_id=principals[2].organization_id,
            code="RC-2026-001",
            status="open",
            note="Lệnh thu hồi mẫu S-38/N3-55.",
            created_by_user_id=principals[2].user_id,
        )
        db.add(recall_order)
        db.flush()

        for label in ("D1", "E1", "F1"):
            db.add(
                RecallOrderLot(
                    recall_order_id=recall_order.id,
                    organization_id=principals[2].organization_id,
                    lot_id=lots[label].id,
                    incident_flag=True,
                )
            )

        db.commit()
        return {label_key: lot.id for label_key, lot in lots.items()}


def ensure_recall_principals(
    db: Session, namespace: UUID = RECALL_NAMESPACE
) -> list[Principal]:
    """Ensure dedicated organizations and actor users exist for the recall namespace."""
    principals = []
    for index, (kind, role, org_name, email_prefix) in enumerate(
        [
            ("farm", "grower", "Nông trại Trại Mát (Thu hồi)", "recall-farm"),
            (
                "cooperative",
                "cooperative",
                "Hợp tác xã Rau Đà Lạt (Thu hồi)",
                "recall-coop",
            ),
            (
                "distribution",
                "distributor",
                "Kho phân phối Rau Việt (Thu hồi)",
                "recall-dist",
            ),
        ]
    ):
        org_id = uuid5(namespace, f"org{index}")
        user_id = uuid5(namespace, f"user{index}")

        org = db.get(Organization, org_id)
        if org is None:
            org = Organization(
                id=org_id,
                name=org_name,
                organization_type=kind,
                is_active=True,
            )
            db.add(org)
            db.flush()

        user = db.get(User, user_id)
        if user is None:
            demo_pw = settings.DEMO_PASSWORD or "DemoSecure2026!"
            user = User(
                id=user_id,
                organization_id=org_id,
                role_code=role,
                email=f"{email_prefix}@example.com",
                full_name=org.name,
                password_hash=hash_password(demo_pw),
                is_active=True,
                failed_login_attempts=0,
            )
            db.add(user)
            db.flush()

        principals.append(
            Principal(
                user.id,
                user.email,
                user.full_name,
                org.id,
                org.name,
                org.organization_type,
                user.role_code,
            )
        )
    return principals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bộ dữ liệu mẫu kịch bản thu hồi 4 tầng (N3-54)"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=str(RECALL_NAMESPACE),
        help="UUID namespace cho bộ dữ liệu mẫu",
    )
    args = parser.parse_args()

    if settings.APP_ENV not in {"development", "staging"} or not settings.DEMO_PASSWORD:
        raise RuntimeError(
            "Seed cần APP_ENV là development/staging và DEMO_PASSWORD rõ ràng."
        )

    namespace = UUID(args.namespace)
    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    try:
        with Session(engine) as db, db.begin():
            _lock_seed(db, namespace)
            principals = ensure_recall_principals(db, namespace)

        ids = seed_recall_workflow(engine, principals, namespace)
        print("Recall seed ready: " + ", ".join(f"{k}={v}" for k, v in ids.items()))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
