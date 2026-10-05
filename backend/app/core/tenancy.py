import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.authorization import has_permission

logger = logging.getLogger(__name__)


def _require_tenant_column(model: Any) -> None:
    if "organization_id" not in model.__table__.c:
        raise TypeError(f"{model.__name__} must have an organization_id column")


def tenant_select(model: Any, principal: Principal | None = None):
    """Build a database-filtered query for an organization-owned model."""
    if principal is None:
        raise ValueError("Tenant context is required for organization-owned queries")

    _require_tenant_column(model)

    if model.__tablename__ in ("lots", "events") and has_permission(
        principal.role, f"{model.__tablename__}:read_all"
    ):
        return select(model)

    return select(model).where(model.organization_id == principal.organization_id)


def get_tenant_record(
    db: Session,
    model: Any,
    record_id: UUID,
    principal: Principal,
) -> Any:
    """Fetch one visible row; never query around RLS to detect foreign rows."""
    statement = tenant_select(model, principal).where(model.id == record_id)
    record = db.scalar(statement)
    if record is not None:
        return record

    logger.warning(
        "Denied access to a record not visible to the caller "
        "user_id=%s organization_id=%s resource_type=%s resource_id=%s",
        principal.user_id,
        principal.organization_id,
        model.__tablename__,
        record_id,
        extra={
            "event": "authorization.record_not_visible",
            "user_id": str(principal.user_id),
            "organization_id": str(principal.organization_id),
            "resource_type": model.__tablename__,
            "resource_id": str(record_id),
        },
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Bạn không có quyền truy cập dữ liệu của tổ chức khác.",
    )
