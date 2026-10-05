"""Tests for N3-21: Immutability and Append-Only guarantees for recorded events.

Validates that no path in the application (API, RBAC, Service, Database Role, Schema)
allows modifying (UPDATE) or deleting (DELETE) any recorded events.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import events as events_endpoint
from app.bootstrap_db_role import _grant_existing_table_permissions
from app.core.auth import Principal, get_current_principal
from app.core.authorization import ROLE_PERMISSIONS, has_permission
from app.core.crypto import (
    GENESIS_PREV_HASH,
    canonicalize_json,
    compute_event_hash,
    sha256_hex,
)
from app.main import app
from app.schemas import event as event_schema
from app.services import event_service


@pytest.fixture
def grower_principal() -> Principal:
    return Principal(
        user_id=uuid4(),
        email="grower@farm.vn",
        full_name="Nguyễn Văn Nông",
        organization_id=uuid4(),
        organization_name="Hợp tác xã Nông trại Xanh",
        organization_type="farm",
        role="grower",
    )


@pytest.fixture
def authenticated_client(grower_principal: Principal) -> TestClient:
    app.dependency_overrides[get_current_principal] = lambda: grower_principal
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    app.dependency_overrides.clear()


# ==============================================================================
# 1. API LAYER: Verifying that no UPDATE or DELETE routes exist
# ==============================================================================


def _get_api_routes():
    from fastapi.routing import APIRoute

    for route in app.routes:
        for context in getattr(route, "effective_route_contexts", lambda: [])():
            if context.path.startswith("/api/v1/"):
                yield context
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            yield route


def test_api_has_no_update_or_delete_routes_for_events():
    """Verify that there are absolutely no PUT, PATCH, or DELETE routes for events."""
    event_routes = [
        route
        for route in _get_api_routes()
        if getattr(route, "path", "").startswith("/api/v1/events")
    ]
    assert len(event_routes) > 0

    prohibited_methods = {"PUT", "PATCH", "DELETE"}
    for route in event_routes:
        methods = getattr(route, "methods", set())
        overlap = methods.intersection(prohibited_methods)
        assert not overlap, (
            f"Violation of N3-21: Route {route.path} exposes prohibited method(s): {overlap}"
        )


def test_http_put_patch_delete_on_events_return_405(
    authenticated_client: TestClient,
):
    """Calling PUT, PATCH, or DELETE on any events endpoint yields 405 Method Not Allowed."""
    random_id = uuid4()

    # Attempt PUT on collection and item
    assert (
        authenticated_client.put(
            "/api/v1/events/", json={"event_type": "tamper"}
        ).status_code
        == 405
    )
    assert (
        authenticated_client.put(
            f"/api/v1/events/{random_id}", json={"event_type": "tamper"}
        ).status_code
        == 405
    )

    # Attempt PATCH on collection and item
    assert (
        authenticated_client.patch(
            "/api/v1/events/", json={"event_type": "tamper"}
        ).status_code
        == 405
    )
    assert (
        authenticated_client.patch(
            f"/api/v1/events/{random_id}", json={"event_type": "tamper"}
        ).status_code
        == 405
    )

    # Attempt DELETE on collection and item
    assert authenticated_client.delete("/api/v1/events/").status_code == 405
    assert authenticated_client.delete(f"/api/v1/events/{random_id}").status_code == 405


# ==============================================================================
# 2. AUTHORIZATION & RBAC LAYER: No update or delete permissions exist
# ==============================================================================


def test_rbac_strictly_forbids_event_mutation():
    """Verify that no role in the entire system possesses an event update or delete permission."""
    for role, permissions in ROLE_PERMISSIONS.items():
        assert "events:update" not in permissions, (
            f"Role '{role}' illegally contains 'events:update'"
        )
        assert "events:delete" not in permissions, (
            f"Role '{role}' illegally contains 'events:delete'"
        )
        assert not has_permission(role, "events:update")
        assert not has_permission(role, "events:delete")


def test_all_operational_roles_have_create_and_read():
    """Operational roles can append and read events, but never mutate them."""
    operational_roles = [
        "grower",
        "cooperative",
        "transporter",
        "distributor",
        "organization_admin",
    ]
    for role in operational_roles:
        assert has_permission(role, "events:create")
        assert has_permission(role, "events:read")
        assert not has_permission(role, "events:update")
        assert not has_permission(role, "events:delete")

    # Inspector can read all events across all organizations, but cannot mutate
    assert has_permission("inspector", "events:read")
    assert has_permission("inspector", "events:read_all")
    assert not has_permission("inspector", "events:create")
    assert not has_permission("inspector", "events:update")
    assert not has_permission("inspector", "events:delete")


# ==============================================================================
# 3. DATABASE ROLE PERMISSIONS LAYER: REVOKE UPDATE, DELETE ON events
# ==============================================================================


def test_bootstrap_db_role_revokes_mutation_on_events_table():
    """Verify that bootstrap_db_role grants only SELECT, INSERT and revokes UPDATE, DELETE."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [
        [("events",), ("lots",), ("farms",)],
        [],  # routines
    ]

    _grant_existing_table_permissions(mock_cursor, app_role="ttcs_app")

    executed_sqls = [str(call[0][0]) for call in mock_cursor.execute.call_args_list]

    assert any("GRANT SELECT, INSERT ON events" in sql for sql in executed_sqls), (
        "Expected GRANT SELECT, INSERT ON events"
    )

    assert any("REVOKE UPDATE, DELETE ON events" in sql for sql in executed_sqls), (
        "Expected REVOKE UPDATE, DELETE ON events"
    )


# ==============================================================================
# 4. SCHEMA AND SERVICE LAYERS: Immutable by construction
# ==============================================================================


def test_schema_has_no_update_schema():
    """Verify that app.schemas.event provides EventCreate and EventRead, but NO EventUpdate."""
    assert hasattr(event_schema, "EventCreate")
    assert hasattr(event_schema, "EventRead")
    assert not hasattr(event_schema, "EventUpdate")


def test_service_has_no_mutation_methods():
    """Verify that event_service has no update or delete functions."""
    assert hasattr(event_service, "record_event")
    assert hasattr(event_service, "list_events_for_lot")
    assert hasattr(event_service, "get_event_by_id")

    assert not hasattr(event_service, "update_event")
    assert not hasattr(event_service, "delete_event")
    assert not hasattr(event_service, "modify_event")
    assert not hasattr(event_service, "remove_event")


def test_endpoints_module_has_no_mutation_handlers():
    """Verify that the events endpoint module does not implement update or delete handlers."""
    assert hasattr(events_endpoint, "list_events")
    assert hasattr(events_endpoint, "create_event")
    assert hasattr(events_endpoint, "get_event")

    assert not hasattr(events_endpoint, "update_event")
    assert not hasattr(events_endpoint, "delete_event")


# ==============================================================================
# 5. CRYPTOGRAPHIC INTEGRITY: RFC 8785 Canonical JSON & SHA-256 Hashing
# ==============================================================================


def test_canonical_json_rfc8785():
    """Verify canonical JSON key sorting and whitespace removal."""
    data1 = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    data2 = {"a": 1, "c": {"x": 10, "y": 20}, "b": 2}

    c1 = canonicalize_json(data1)
    c2 = canonicalize_json(data2)

    assert c1 == c2
    assert c1 == '{"a":1,"b":2,"c":{"x":10,"y":20}}'


def test_canonical_json_preserves_vietnamese_characters():
    """Verify Vietnamese Unicode characters are properly preserved without escaping."""
    data = {"nong_san": "Cà chua VietGAP", "nhiet_do": 4.5}
    canonical = canonicalize_json(data)
    assert "Cà chua VietGAP" in canonical


def test_sha256_hex_length_and_avalanche_effect():
    """Verify SHA-256 length and sensitive tamper detection."""
    hash1 = sha256_hex("data_sample_1")
    hash2 = sha256_hex("data_sample_2")

    assert len(hash1) == 64
    assert len(hash2) == 64
    assert hash1 != hash2


def test_event_hash_chaining_genesis_and_step():
    """Verify event hash chaining from genesis to consecutive events."""
    lot_id = str(uuid4())
    org_id = str(uuid4())

    # Genesis event
    payload1 = {"temperature_c": 4.2, "status": "harvested"}
    hash1 = compute_event_hash(
        GENESIS_PREV_HASH,
        {
            "event_type": "harvest",
            "lot_id": lot_id,
            "organization_id": org_id,
            "payload": payload1,
            "sequence_number": 1,
        },
    )
    assert len(hash1) == 64

    # Second event chained to first event
    payload2 = {"temperature_c": 3.8, "status": "in_transit"}
    hash2 = compute_event_hash(
        hash1,
        {
            "event_type": "transport",
            "lot_id": lot_id,
            "organization_id": org_id,
            "payload": payload2,
            "sequence_number": 2,
        },
    )
    assert len(hash2) == 64
    assert hash2 != hash1

    # Tamper detection: if someone secretly altered event 1's temperature to 99.9°C
    tampered_payload1 = {"temperature_c": 99.9, "status": "harvested"}
    tampered_hash1 = compute_event_hash(
        GENESIS_PREV_HASH,
        {
            "event_type": "harvest",
            "lot_id": lot_id,
            "organization_id": org_id,
            "payload": tampered_payload1,
            "sequence_number": 1,
        },
    )
    assert tampered_hash1 != hash1
