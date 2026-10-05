import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import Principal, get_current_principal

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "grower": frozenset(
        {
            "auth:session",
            "farms:read",
            "farms:write",
            "lots:read",
            "events:read",
            "events:create",
        }
    ),
    "cooperative": frozenset(
        {"auth:session", "lots:read", "events:read", "events:create"}
    ),
    "transporter": frozenset(
        {"auth:session", "lots:read", "events:read", "events:create"}
    ),
    "distributor": frozenset(
        {"auth:session", "lots:read", "events:read", "events:create"}
    ),
    "inspector": frozenset({"auth:session", "lots:read_all", "events:read_all"}),
    "organization_admin": frozenset(
        {
            "auth:session",
            "farms:read",
            "farms:write",
            "lots:read",
            "events:read",
            "events:create",
        }
    ),
    "system_admin": frozenset({"auth:session"}),
}


def has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, frozenset())
    if permission in permissions:
        return True
    if permission == "lots:read" and "lots:read_all" in permissions:
        return True
    if permission == "events:read" and "events:read_all" in permissions:
        return True
    return False


def require_permission(
    permission: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare the permission a business API route requires."""

    def decorator(endpoint: Callable[..., Any]) -> Callable[..., Any]:
        endpoint.__required_permission__ = permission  # type: ignore[attr-defined]
        return endpoint

    return decorator


def enforce_route_permission(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> None:
    route = request.scope.get("route")
    endpoint = getattr(route, "endpoint", None)
    permission = getattr(endpoint, "__required_permission__", None)

    request.state.principal = principal
    request.state.organization_id = principal.organization_id

    if permission is None:
        logger.warning(
            "Denied API route without a declared permission "
            "user_id=%s organization_id=%s method=%s path=%s",
            principal.user_id,
            principal.organization_id,
            request.method,
            request.url.path,
            extra={
                "event": "authorization.route_missing_permission",
                "user_id": str(principal.user_id),
                "organization_id": str(principal.organization_id),
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập của API chưa được cấu hình.",
        )

    if not has_permission(principal.role, permission):
        logger.warning(
            "Denied API route due to insufficient permission "
            "user_id=%s organization_id=%s role=%s permission=%s method=%s path=%s",
            principal.user_id,
            principal.organization_id,
            principal.role,
            permission,
            request.method,
            request.url.path,
            extra={
                "event": "authorization.permission_denied",
                "user_id": str(principal.user_id),
                "organization_id": str(principal.organization_id),
                "role": principal.role,
                "permission": permission,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện thao tác này.",
        )
