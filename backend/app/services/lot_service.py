import base64
import json
from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.lot_codes import generate_lot_code
from app.core.tenancy import get_tenant_record, tenant_select
from app.models.farm import Farm
from app.models.lot import Lot
from app.models.product import Product
from app.schemas.lot import LotCreate
from app.services import event_service


def create_harvest_lot(
    db: Session,
    principal: Principal,
    lot_in: LotCreate,
) -> Lot:
    farm = get_tenant_record(db, Farm, lot_in.farm_id, principal)
    product = db.scalar(select(Product).where(Product.id == lot_in.product_id))
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy sản phẩm trong danh mục.",
        )

    for _ in range(5):
        lot_code = generate_lot_code()
        lot = Lot(
            organization_id=principal.organization_id,
            current_holder_organization_id=principal.organization_id,
            farm_id=farm.id,
            name=product.name,
            lot_code=lot_code,
            product_id=product.id,
            harvested_on=lot_in.harvested_on,
            quantity=lot_in.quantity,
            remaining_quantity=lot_in.quantity,
            status="active",
        )
        try:
            with db.begin_nested():
                db.add(lot)
                db.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            if getattr(diagnostic, "constraint_name", None) != "uq_lots_lot_code":
                raise
            continue

        try:
            event_service.append_event(
                db,
                principal,
                lot.id,
                event_type="harvest_recorded",
                payload={
                    "lot_code": lot_code,
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "harvested_on": lot_in.harvested_on.isoformat(),
                    "quantity": format(lot_in.quantity, "f"),
                    "unit": product.unit,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(lot)
        return lot

    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Không thể cấp mã lô duy nhất lúc này. Vui lòng thử lại.",
    )


def _encode_cursor(lot: Lot) -> str:
    payload = json.dumps(
        {
            "harvested_on": lot.harvested_on.isoformat() if lot.harvested_on else None,
            "id": str(lot.id),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date | None, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        harvested_on = (
            date.fromisoformat(value["harvested_on"]) if value["harvested_on"] else None
        )
        return harvested_on, UUID(value["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Con trỏ phân trang không hợp lệ.",
        ) from error


def list_lots(
    db: Session,
    principal: Principal,
    *,
    query: str | None,
    product_id: UUID | None,
    cursor: str | None,
    page_size: int,
) -> dict:
    statement = tenant_select(Lot, principal)
    if query:
        escaped_query = (
            query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        statement = statement.where(
            Lot.lot_code.ilike(f"%{escaped_query}%", escape="\\")
        )
    if product_id:
        statement = statement.where(Lot.product_id == product_id)

    if cursor:
        cursor_date, cursor_id = _decode_cursor(cursor)
        if cursor_date is None:
            statement = statement.where(Lot.harvested_on.is_(None), Lot.id < cursor_id)
        else:
            statement = statement.where(
                or_(
                    Lot.harvested_on < cursor_date,
                    and_(Lot.harvested_on == cursor_date, Lot.id < cursor_id),
                    Lot.harvested_on.is_(None),
                )
            )

    # Limit before eager-loading product/holder/location. Otherwise PostgreSQL
    # may evaluate tenant-protected joins for thousands of rows before sorting.
    page = (
        statement.with_only_columns(Lot.id)
        .order_by(Lot.harvested_on.desc().nulls_last(), Lot.id.desc())
        .limit(page_size + 1)
        .cte("lot_page")
        .prefix_with("MATERIALIZED")
    )
    fetched = list(
        db.scalars(
            select(Lot)
            .join(page, page.c.id == Lot.id)
            .order_by(Lot.harvested_on.desc().nulls_last(), Lot.id.desc())
        ).all()
    )
    has_more = len(fetched) > page_size
    items = fetched[:page_size]
    return {
        "items": items,
        "next_cursor": _encode_cursor(items[-1]) if has_more and items else None,
    }
