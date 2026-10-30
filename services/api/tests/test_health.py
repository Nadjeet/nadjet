import asyncio

from fastapi.testclient import TestClient

from nadjet_api import __version__
from nadjet_api.config import Settings
from nadjet_api.health import Probe, run_probes
from nadjet_api.main import create_app

SETTINGS = Settings(env="test", readiness_timeout_s=0.2)


def ok(detail: str) -> Probe:
    async def probe() -> str:
        return detail

    return probe


def failing(exc: Exception) -> Probe:
    async def probe() -> str:
        raise exc

    return probe


def slow() -> Probe:
    async def probe() -> str:
        await asyncio.sleep(5)
        return "never"

    return probe


def client(probes: dict[str, Probe]) -> TestClient:
    return TestClient(create_app(SETTINGS, probes=probes))


def test_health_reports_version() -> None:
    with client({}) as c:
        response = c.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_ready_ok_when_all_dependencies_answer() -> None:
    with client({"database": ok("postgis 3.5"), "redis": ok("pong")}) as c:
        response = c.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"] == {"ok": True, "detail": "postgis 3.5"}


def test_ready_503_and_details_when_a_dependency_fails() -> None:
    probes = {"database": ok("postgis 3.5"), "redis": failing(ConnectionError("refused"))}
    with client(probes) as c:
        response = c.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["redis"] == {"ok": False, "detail": "ConnectionError: refused"}
    assert body["dependencies"]["database"]["ok"] is True


async def test_probe_timeout_is_reported_not_raised() -> None:
    [result] = await run_probes({"database": slow()}, timeout_s=0.05)
    assert result.ok is False
    assert "timed out" in result.detail


def test_cors_allows_configured_origin() -> None:
    with client({}) as c:
        response = c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
