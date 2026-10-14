"""Seed local demo organizations, users, farms, products, and end-to-end workflows."""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import settings
from app.core.security import hash_password
from app.models.farm import Farm
from app.models.handover import Handover
from app.models.identity import Organization, Role, User
from app.models.lot import Lot
from app.models.product import Product
from app.schemas.handover import HandoverCreate
from app.schemas.location import LocationCreate, LotConsume, LotMove
from app.schemas.lot import LotCreate
from app.seed_lineage_workflow import seed_workflow
from app.services import (
    event_service,
    handover_service,
    lot_lifecycle_service,
    lot_service,
)

logger = logging.getLogger(__name__)

DEMO_WORKFLOW_NAMESPACE = UUID("dd4fa977-8933-4c0a-bf32-236ac67f8099")

FARM_ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
COOP_ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
INSPECT_ORG_ID = UUID("33333333-3333-4333-8333-333333333333")
ADMIN_ORG_ID = UUID("44444444-4444-4444-8444-444444444444")
DIST_ORG_ID = UUID("55555555-5555-4555-8555-555555555555")

GROWER_USER_ID = UUID("aaaa1111-1111-4111-8111-111111111111")
COOP_USER_ID = UUID("bbbb2222-2222-4222-8222-222222222222")
INSPECT_USER_ID = UUID("cccc3333-3333-4333-8333-333333333333")
ADMIN_USER_ID = UUID("dddd4444-4444-4444-8444-444444444444")
DIST_USER_ID = UUID("eeee5555-5555-4555-8555-555555555555")

FARM_A1_ID = UUID("f1111111-1111-4111-8111-111111111111")
FARM_B2_ID = UUID("f2222222-2222-4222-8222-222222222222")
FARM_C1_ID = UUID("f3333333-3333-4333-8333-333333333333")

STRAWBERRY_PRODUCT_ID = UUID("66666666-6666-4666-8666-666666666601")
HYDRO_VEG_PRODUCT_ID = UUID("66666666-6666-4666-8666-666666666602")
SHAN_TEA_PRODUCT_ID = UUID("66666666-6666-4666-8666-666666666603")

DEMO_ORGANIZATIONS = [
    {
        "id": FARM_ORG_ID,
        "name": "Nông trại Cầu Đất Đà Lạt",
        "organization_type": "farm",
    },
    {
        "id": COOP_ORG_ID,
        "name": "Hợp tác xã Nông sản Mộc Châu",
        "organization_type": "cooperative",
    },
    {
        "id": INSPECT_ORG_ID,
        "name": "Chi cục Quản lý Chất lượng Nông lâm sản",
        "organization_type": "inspection",
    },
    {
        "id": ADMIN_ORG_ID,
        "name": "Cục Quản trị Hệ thống Chuỗi lạnh Quốc gia",
        "organization_type": "administration",
    },
    {
        "id": DIST_ORG_ID,
        "name": "Trung tâm Phân phối Chuỗi lạnh Việt",
        "organization_type": "distribution",
    },
]

DEMO_USERS = [
    {
        "id": GROWER_USER_ID,
        "organization_id": FARM_ORG_ID,
        "role_code": "grower",
        "email": "grower@caudat.vn",
        "full_name": "Nguyễn Văn Minh (Nông hộ Cầu Đất)",
    },
    {
        "id": COOP_USER_ID,
        "organization_id": COOP_ORG_ID,
        "role_code": "organization_admin",
        "email": "admin@mocchau.vn",
        "full_name": "Trần Thị Hương (Quản trị HTX Mộc Châu)",
    },
    {
        "id": INSPECT_USER_ID,
        "organization_id": INSPECT_ORG_ID,
        "role_code": "inspector",
        "email": "inspector@chicuc.gov.vn",
        "full_name": "Lê Hoàng Nam (Thanh tra viên)",
    },
    {
        "id": ADMIN_USER_ID,
        "organization_id": ADMIN_ORG_ID,
        "role_code": "system_admin",
        "email": "admin@system.vn",
        "full_name": "Vũ Hải Đăng (Quản trị hệ thống)",
    },
    {
        "id": DIST_USER_ID,
        "organization_id": DIST_ORG_ID,
        "role_code": "distributor",
        "email": "distributor@phanphoi.vn",
        "full_name": "Phạm Quốc Bảo (Nhà phân phối Chuỗi lạnh)",
    },
]

DEMO_FARMS = [
    {
        "id": FARM_A1_ID,
        "organization_id": FARM_ORG_ID,
        "name": "Khu nhà kính Dâu tây Công nghệ cao A1",
        "area_ha": Decimal("2.4500"),
        "latitude": Decimal("11.862450"),
        "longitude": Decimal("108.538120"),
    },
    {
        "id": FARM_B2_ID,
        "organization_id": FARM_ORG_ID,
        "name": "Thửa đất Rau thủy canh Đà Lạt B2",
        "area_ha": Decimal("1.8000"),
        "latitude": Decimal("11.865100"),
        "longitude": Decimal("108.541300"),
    },
    {
        "id": FARM_C1_ID,
        "organization_id": COOP_ORG_ID,
        "name": "Vùng trồng Chè Shan Tuyết Mộc Châu C1",
        "area_ha": Decimal("5.2000"),
        "latitude": Decimal("20.844500"),
        "longitude": Decimal("104.639200"),
    },
]

DEMO_PRODUCTS = [
    {
        "id": STRAWBERRY_PRODUCT_ID,
        "name": "Dâu tây Cầu Đất",
        "unit": "kg",
        "price": Decimal("180000.00"),
        "quantity": 500,
        "description": (
            "Dâu tây giống Nhật thu hoạch tại nhà kính Cầu Đất, bảo quản lạnh 2–4°C."
        ),
    },
    {
        "id": HYDRO_VEG_PRODUCT_ID,
        "name": "Rau thủy canh Đà Lạt",
        "unit": "kg",
        "price": Decimal("45000.00"),
        "quantity": 300,
        "description": (
            "Xà lách và cải bó xôi thủy canh đạt chuẩn VietGAP, bảo quản mát 4–8°C."
        ),
    },
    {
        "id": SHAN_TEA_PRODUCT_ID,
        "name": "Chè Shan Tuyết Mộc Châu",
        "unit": "kg",
        "price": Decimal("350000.00"),
        "quantity": 200,
        "description": (
            "Búp chè tươi thu hái vùng cao nguyên, kiểm soát độ ẩm và nhiệt độ."
        ),
    },
]

DEMO_LOCATIONS = [
    {
        "name": "Kho lạnh Trung tâm Quận 7",
        "address": "Lô C1, Đường số 7, KCN Tân Thuận, Quận 7, TP.HCM",
    },
    {
        "name": "Cửa hàng Rau sạch Quận 1",
        "address": "125 Nguyễn Thị Minh Khai, Phường Bến Thành, Quận 1, TP.HCM",
    },
]


def _seed_operational_demo_lots(
    session: Session,
    grower_principal: Principal,
    coop_principal: Principal,
    strawberry_product_id: UUID,
) -> None:
    """Seed ready-to-use active lots and an overdue handover for Sprint 1-4 demos."""
    existing_lot = session.scalar(
        select(Lot.id).where(Lot.product_id == strawberry_product_id).limit(1)
    )
    if existing_lot is not None:
        return

    harvest_date = date(2026, 10, 1)

    # 1. Active 40 kg lot at Farm (ready for Step 4 cold-chain event & Step 5 handover)
    farm_active = lot_service.create_harvest_lot(
        session,
        grower_principal,
        LotCreate(
            farm_id=FARM_A1_ID,
            product_id=strawberry_product_id,
            harvested_on=harvest_date,
            quantity=Decimal("40.000"),
        ),
    )
    farm_active.name = (
        "Dâu tây Cầu Đất — Lô nông trại 40kg (Sẵn sàng ghi sự kiện / bàn giao)"
    )
    session.flush()
    event_service.append_event(
        session,
        grower_principal,
        farm_active.id,
        event_type="cold_storage",
        payload={
            "location": "Kho lạnh sơ chế Cầu Đất A1",
            "temperature_c": 3.2,
            "note": "Làm lạnh nhanh sau thu hoạch đạt chuẩn 2–4°C.",
        },
    )
    session.commit()

    # 2. Active 40 kg lot at Cooperative (ready for Step 6 Split 40 kg -> 10 + 20 kg)
    coop_split_lot = lot_service.create_harvest_lot(
        session,
        grower_principal,
        LotCreate(
            farm_id=FARM_A1_ID,
            product_id=strawberry_product_id,
            harvested_on=harvest_date,
            quantity=Decimal("40.000"),
        ),
    )
    coop_split_lot.name = "Dâu tây Cầu Đất — Lô HTX 40kg (Sẵn sàng tách lô)"
    session.flush()
    h_split = handover_service.create_handover(
        session,
        grower_principal,
        HandoverCreate(
            lot_id=coop_split_lot.id,
            to_organization_id=coop_principal.organization_id,
            note="Bàn giao lô 40kg sang HTX Mộc Châu để phân loại và tách lô.",
        ),
    )
    handover_service.accept_handover(session, coop_principal, h_split["id"])

    # 3 & 4. Two active lots of the same product at Cooperative (ready for Step 7)
    for label_suffix, qty in (
        ("Lô thành phần A (Sẵn sàng gộp lô)", Decimal("20.000")),
        ("Lô thành phần B (Sẵn sàng gộp lô)", Decimal("25.000")),
    ):
        merge_candidate = lot_service.create_harvest_lot(
            session,
            grower_principal,
            LotCreate(
                farm_id=FARM_B2_ID,
                product_id=strawberry_product_id,
                harvested_on=harvest_date,
                quantity=qty,
            ),
        )
        merge_candidate.name = f"Dâu tây Cầu Đất — {label_suffix}"
        session.flush()
        h_merge = handover_service.create_handover(
            session,
            grower_principal,
            HandoverCreate(
                lot_id=merge_candidate.id,
                to_organization_id=coop_principal.organization_id,
                note="Bàn giao lô thành phần cùng sản phẩm về HTX để gộp lô.",
            ),
        )
        handover_service.accept_handover(session, coop_principal, h_merge["id"])

    # 5. Overdue pending handover (49h old, scanned so overdue_at is set for Step 12)
    overdue_lot = lot_service.create_harvest_lot(
        session,
        grower_principal,
        LotCreate(
            farm_id=FARM_A1_ID,
            product_id=strawberry_product_id,
            harvested_on=harvest_date,
            quantity=Decimal("25.000"),
        ),
    )
    overdue_lot.name = "Dâu tây Cầu Đất — Lô chờ xác nhận (Quá hạn 48h)"
    session.flush()
    h_overdue = handover_service.create_handover(
        session,
        grower_principal,
        HandoverCreate(
            lot_id=overdue_lot.id,
            to_organization_id=coop_principal.organization_id,
            note="Yêu cầu bàn giao quá 48 giờ để trình diễn cảnh báo quá hạn.",
        ),
    )
    now = datetime.now(UTC)
    handover_row = session.get(Handover, h_overdue["id"])
    if handover_row is not None:
        handover_row.created_at = now - timedelta(hours=49)
        handover_row.overdue_at = now
        session.commit()


def seed_demo_data() -> None:
    if settings.APP_ENV not in ("development", "staging"):
        return

    demo_password = settings.DEMO_PASSWORD or "Password123!"

    engine = create_engine(settings.MIGRATION_DATABASE_URL, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            if session.scalar(select(Role.code).limit(1)) is None:
                return

            password_hash = hash_password(demo_password)

            for org_data in DEMO_ORGANIZATIONS:
                org = session.get(Organization, org_data["id"])
                if org is None:
                    session.add(
                        Organization(
                            id=org_data["id"],
                            name=org_data["name"],
                            organization_type=org_data["organization_type"],
                            is_active=True,
                        )
                    )
                else:
                    org.name = org_data["name"]
                    org.organization_type = org_data["organization_type"]
                    org.is_active = True

            session.flush()

            for user_data in DEMO_USERS:
                existing_user = session.scalar(
                    select(User).where(User.email == user_data["email"])
                )
                if existing_user is None:
                    session.add(
                        User(
                            id=user_data["id"],
                            organization_id=user_data["organization_id"],
                            role_code=user_data["role_code"],
                            email=user_data["email"],
                            full_name=user_data["full_name"],
                            password_hash=password_hash,
                            failed_login_attempts=0,
                            locked_until=None,
                            is_active=True,
                        )
                    )
                else:
                    existing_user.organization_id = user_data["organization_id"]
                    existing_user.role_code = user_data["role_code"]
                    existing_user.full_name = user_data["full_name"]
                    existing_user.password_hash = password_hash
                    existing_user.failed_login_attempts = 0
                    existing_user.locked_until = None
                    existing_user.is_active = True

            session.flush()

            for farm_data in DEMO_FARMS:
                existing_farm = session.get(Farm, farm_data["id"])
                if existing_farm is None:
                    session.add(
                        Farm(
                            id=farm_data["id"],
                            organization_id=farm_data["organization_id"],
                            name=farm_data["name"],
                            area_ha=farm_data["area_ha"],
                            latitude=farm_data["latitude"],
                            longitude=farm_data["longitude"],
                        )
                    )

            session.commit()

            # Allow table-owner migration connections on managed PostgreSQL
            # (non-superuser) to seed products while keeping RLS active for app role.
            session.execute(text("ALTER TABLE products NO FORCE ROW LEVEL SECURITY"))
            session.execute(
                text("ALTER TABLE integrity_checks NO FORCE ROW LEVEL SECURITY")
            )
            session.commit()

            strawberry_product_id = STRAWBERRY_PRODUCT_ID
            for product_data in DEMO_PRODUCTS:
                existing_product = session.get(Product, product_data["id"])
                if existing_product is None:
                    existing_product = session.scalar(
                        select(Product).where(
                            func.lower(Product.name) == product_data["name"].lower()
                        )
                    )
                if existing_product is None:
                    existing_product = Product(
                        id=product_data["id"],
                        name=product_data["name"],
                        unit=product_data["unit"],
                        price=product_data["price"],
                        quantity=product_data["quantity"],
                        description=product_data["description"],
                    )
                    session.add(existing_product)
                    session.flush()
                if product_data["id"] == STRAWBERRY_PRODUCT_ID:
                    strawberry_product_id = existing_product.id

            session.commit()

            grower_principal = Principal(
                user_id=GROWER_USER_ID,
                email="grower@caudat.vn",
                full_name="Nguyễn Văn Minh (Nông hộ Cầu Đất)",
                organization_id=FARM_ORG_ID,
                organization_name="Nông trại Cầu Đất Đà Lạt",
                organization_type="farm",
                role="grower",
            )
            coop_principal = Principal(
                user_id=COOP_USER_ID,
                email="admin@mocchau.vn",
                full_name="Trần Thị Hương (Quản trị HTX Mộc Châu)",
                organization_id=COOP_ORG_ID,
                organization_name="Hợp tác xã Nông sản Mộc Châu",
                organization_type="cooperative",
                role="organization_admin",
            )
            dist_principal = Principal(
                user_id=DIST_USER_ID,
                email="distributor@phanphoi.vn",
                full_name="Phạm Quốc Bảo (Nhà phân phối Chuỗi lạnh)",
                organization_id=DIST_ORG_ID,
                organization_name="Trung tâm Phân phối Chuỗi lạnh Việt",
                organization_type="distribution",
                role="distributor",
            )

            locations = []
            try:
                existing_locations = lot_lifecycle_service.list_locations(
                    session, dist_principal
                )
                existing_loc_names = {loc.name for loc in existing_locations}
                for loc_data in DEMO_LOCATIONS:
                    if loc_data["name"] not in existing_loc_names:
                        lot_lifecycle_service.create_location(
                            session,
                            dist_principal,
                            LocationCreate(
                                name=loc_data["name"],
                                address=loc_data["address"],
                            ),
                        )
                locations = lot_lifecycle_service.list_locations(
                    session, dist_principal
                )
            except Exception:
                session.rollback()
                logger.exception("Failed seeding demo distribution locations.")

            try:
                # Seed the 18-lot Bắp cải xanh 4-tier split/merge workflow
                workflow_ids = seed_workflow(
                    engine,
                    [grower_principal, coop_principal, dist_principal],
                    namespace=DEMO_WORKFLOW_NAMESPACE,
                )
                session.expire_all()
                d1_lot = session.get(Lot, workflow_ids["D1"])
                d2_lot = session.get(Lot, workflow_ids["D2"])
                if (
                    locations
                    and d1_lot is not None
                    and d1_lot.current_location_id is None
                    and d1_lot.status == "active"
                ):
                    lot_lifecycle_service.move_lot(
                        session,
                        dist_principal,
                        d1_lot.id,
                        LotMove(
                            location_id=locations[0].id,
                            note="Nhập kho lạnh trung tâm chuẩn bị phân phối.",
                        ),
                    )
                if locations and d2_lot is not None and d2_lot.status == "active":
                    target_loc = locations[1] if len(locations) > 1 else locations[0]
                    lot_lifecycle_service.move_lot(
                        session,
                        dist_principal,
                        d2_lot.id,
                        LotMove(
                            location_id=target_loc.id,
                            note="Xuất sang cửa hàng bán lẻ.",
                        ),
                    )
                    lot_lifecycle_service.consume_lot(
                        session,
                        dist_principal,
                        d2_lot.id,
                        LotConsume(
                            note=(
                                "Đã bán lẻ hết tại cửa hàng phân phối (trạng thái kết thúc)."
                            )
                        ),
                    )
            except Exception:
                session.rollback()
                logger.exception("Failed seeding 18-lot lineage workflow.")

            try:
                _seed_operational_demo_lots(
                    session,
                    grower_principal,
                    coop_principal,
                    strawberry_product_id,
                )
            except Exception:
                session.rollback()
                logger.exception("Failed seeding operational demo lots.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed_demo_data()
