import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_checks_database_and_masks_failure(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.main import engine

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).status_code == 200

        def unavailable():
            raise OperationalError("sensitive database URL", {}, Exception("secret"))

        monkeypatch.setattr(engine, "connect", unavailable)
        response = await client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_version_exposes_only_a_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/version")).json() == {"commit": "a" * 40}
        monkeypatch.setenv("RENDER_GIT_COMMIT", "not-a-commit")
        assert (await client.get("/version")).json() == {"commit": None}


@pytest.mark.asyncio
async def test_lifespan_runs_maintenance_and_cancels_it_on_shutdown(monkeypatch):
    import asyncio

    from app.jobs import scheduler
    from app.main import lifespan

    monkeypatch.setattr(scheduler, "last_success", None)
    async with lifespan(app):
        for _ in range(100):
            if scheduler.last_success is not None:
                break
            await asyncio.sleep(0.01)
        assert scheduler.last_success is not None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code == 200
    assert app.state.maintenance_started is False


@pytest.mark.asyncio
async def test_demo_items_route_is_removed():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/items/")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_check_html_landing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "AgroChain Backend API" in response.text
    assert "https://ttcs-frontend-staging.onrender.com" in response.text


@pytest.mark.asyncio
async def test_custom_404_html_and_json():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_html = await client.get(
            "/ttcs-backend-staging.onrender.com",
            headers={"Accept": "text/html"},
        )
        assert res_html.status_code == 404
        assert "404" in res_html.text

        res_json = await client.get(
            "/ttcs-backend-staging.onrender.com",
            headers={"Accept": "application/json"},
        )
        assert res_json.status_code == 404
        assert res_json.json()["detail"] == "Not Found"
