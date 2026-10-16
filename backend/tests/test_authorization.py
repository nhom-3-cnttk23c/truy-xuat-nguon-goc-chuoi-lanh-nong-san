from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.core.auth import Principal
from app.core.authorization import (
    enforce_route_permission,
    has_permission,
    require_permission,
)


@pytest.mark.parametrize("role", ["cooperative", "distributor", "organization_admin"])
def test_lot_transform_permission_is_separate_from_harvest_permission(role):
    assert has_permission(role, "lots:transform") is True


@pytest.mark.parametrize("role", ["grower", "transporter", "inspector", "system_admin"])
def test_roles_without_processing_responsibility_cannot_transform_lots(role):
    assert has_permission(role, "lots:transform") is False


def test_system_admin_has_highest_privileges():
    # system_admin must have all system permissions
    all_known_permissions = [
        "auth:session",
        "farms:read",
        "farms:write",
        "farms:read_all",
        "lots:read",
        "lots:read_all",
        "events:read",
        "events:read_all",
        "products:read",
        "products:write",
        "products:read_all",
        "events:verify",
        "security:read",
    ]
    for perm in all_known_permissions:
        assert has_permission("system_admin", perm) is True, (
            f"system_admin must have {perm}"
        )


def test_organization_admin_permissions():
    assert has_permission("organization_admin", "farms:read") is True
    assert has_permission("organization_admin", "farms:write") is True
    assert has_permission("organization_admin", "lots:read") is True
    assert has_permission("organization_admin", "lots:write") is False
    assert has_permission("organization_admin", "products:read") is True
    assert has_permission("organization_admin", "products:write") is False
    assert has_permission("organization_admin", "security:read") is False
    assert has_permission("organization_admin", "lots:read_all") is False


def test_grower_cannot_write_products_or_read_all_lots():
    assert has_permission("grower", "products:write") is False
    assert has_permission("grower", "lots:read_all") is False
    assert has_permission("grower", "farms:read") is True
    assert has_permission("grower", "farms:write") is True


@pytest.mark.parametrize(
    "role",
    [
        "grower",
        "cooperative",
        "transporter",
        "distributor",
        "inspector",
        "organization_admin",
    ],
)
def test_only_system_admin_can_manage_shared_catalog_and_security(role: str):
    assert has_permission(role, "products:write") is False
    assert has_permission(role, "security:read") is False


@pytest.mark.parametrize("role", ["inspector", "system_admin"])
def test_only_auditor_roles_can_verify_event_integrity(role: str):
    assert has_permission(role, "events:verify") is True


@pytest.mark.parametrize(
    "role",
    ["grower", "cooperative", "transporter", "distributor", "organization_admin"],
)
def test_business_roles_cannot_verify_event_integrity(role: str):
    assert has_permission(role, "events:verify") is False


def test_system_admin_can_audit_but_cannot_act_as_a_chain_participant():
    assert has_permission("system_admin", "lots:read_all") is True
    assert has_permission("system_admin", "events:read_all") is True
    assert has_permission("system_admin", "events:verify") is True
    assert has_permission("system_admin", "lots:create") is False
    assert has_permission("system_admin", "lots:write") is False
    assert has_permission("system_admin", "events:create") is False
    assert has_permission("system_admin", "handovers:create") is False
    assert has_permission("system_admin", "handovers:resolve") is False


@pytest.mark.parametrize(
    "permission",
    ["lots:create", "events:create", "handovers:create", "handovers:resolve"],
)
def test_system_admin_chain_mutations_are_denied_at_route_boundary(permission: str):
    @require_permission(permission)
    def chain_mutation():
        return None

    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/products/",
            "raw_path": b"/api/v1/products/",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 123),
            "server": ("testserver", 443),
            "route": SimpleNamespace(endpoint=chain_mutation),
        }
    )
    principal = Principal(
        user_id=uuid4(),
        email="admin@system.vn",
        full_name="System admin",
        organization_id=uuid4(),
        organization_name="Administration",
        organization_type="administration",
        role="system_admin",
    )

    with pytest.raises(HTTPException) as error:
        enforce_route_permission(request, principal)

    assert error.value.status_code == 403


def test_organization_admin_product_write_is_denied_at_route_boundary():
    @require_permission("products:write")
    def create_product():
        return None

    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/products/",
            "raw_path": b"/api/v1/products/",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 123),
            "server": ("testserver", 443),
            "route": SimpleNamespace(endpoint=create_product),
        }
    )
    principal = Principal(
        user_id=uuid4(),
        email="admin@example.com",
        full_name="Organization admin",
        organization_id=uuid4(),
        organization_name="Test organization",
        organization_type="cooperative",
        role="organization_admin",
    )

    with pytest.raises(HTTPException) as error:
        enforce_route_permission(request, principal)

    assert error.value.status_code == 403


@pytest.mark.parametrize("role", ["inspector", "organization_admin", "system_admin"])
def test_roles_authorized_to_open_recalls(role):
    assert has_permission(role, "recalls:open") is True


@pytest.mark.parametrize(
    "role", ["grower", "cooperative", "distributor", "transporter"]
)
def test_roles_unauthorized_to_open_recalls(role):
    assert has_permission(role, "recalls:open") is False


@pytest.mark.parametrize(
    "role",
    [
        "grower",
        "cooperative",
        "distributor",
        "transporter",
        "inspector",
        "organization_admin",
        "system_admin",
    ],
)
def test_all_authenticated_roles_can_read_recalls(role):
    assert has_permission(role, "recalls:read") is True


@pytest.mark.parametrize(
    "role",
    ["transporter", "cooperative", "distributor", "organization_admin", "system_admin"],
)
def test_roles_authorized_to_manage_shipments(role):
    assert has_permission(role, "shipments:create") is True
    assert has_permission(role, "shipments:read") is True
    assert has_permission(role, "shipments:complete") is True


@pytest.mark.parametrize("role", ["grower", "inspector"])
def test_roles_unauthorized_to_create_shipments(role):
    assert has_permission(role, "shipments:create") is False


def test_inspector_can_read_all_shipments():
    assert has_permission("inspector", "shipments:read") is True
    assert has_permission("inspector", "shipments:read_all") is True
    assert has_permission("inspector", "shipments:complete") is False
