from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, set_db_context
from app.core.security import hash_session_token
from app.models.identity import AuthSession, Organization, Role, User


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str
    full_name: str
    organization_id: UUID
    organization_name: str
    organization_type: str
    role: str


def extract_session_token(request: Request) -> str | None:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        return token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def get_current_principal(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Principal:
    token = extract_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Cần đăng nhập."
        )

    token_hash = hash_session_token(token)
    set_db_context(db, session_token_hash=token_hash)
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
    )
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )

    now = datetime.now(UTC)
    if auth_session.expires_at <= now:
        auth_session.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn.",
        )

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )

    organization = db.get(Organization, user.organization_id)
    role = db.get(Role, user.role_code)
    if organization is None or role is None or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )

    return Principal(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization_id=user.organization_id,
        organization_name=organization.name,
        organization_type=organization.organization_type,
        role=role.code,
    )
