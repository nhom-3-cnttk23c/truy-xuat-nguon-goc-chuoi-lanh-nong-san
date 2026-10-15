"""API endpoints for managing recall orders (N3-49)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.authorization import require_permission
from app.core.database import get_db
from app.schemas.recall import RecallCreate, RecallOrderRead
from app.services import recall_service

router = APIRouter()


@router.post(
    "/",
    response_model=RecallOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Mở lệnh thu hồi cho lô có sự cố",
)
@require_permission("recalls:open")
def open_recall_order(
    payload: RecallCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RecallOrderRead:
    return recall_service.open_recall(db, principal, payload)


@router.get(
    "/",
    response_model=list[RecallOrderRead],
    summary="Danh sách lệnh thu hồi",
)
@require_permission("recalls:read")
def list_recall_orders(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[RecallOrderRead]:
    return recall_service.list_recalls(db, principal)


@router.get(
    "/{recall_id}",
    response_model=RecallOrderRead,
    summary="Chi tiết lệnh thu hồi",
)
@require_permission("recalls:read")
def get_recall_order(
    recall_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RecallOrderRead:
    return recall_service.get_recall(db, principal, recall_id)
