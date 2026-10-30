"""Integration: the real readiness probes against the local PostGIS and Redis (`make infra`).

These tests fail (they do not skip) when the infrastructure is down, so a green run always
means the dependencies were actually reached.
"""

import pytest
from fastapi.testclient import TestClient

from nadjet_api.config import Settings
from nadjet_api.main import create_app

pytestmark = pytest.mark.integration


def test_ready_reaches_postgis_and_redis() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/ready")
    body = response.json()
    assert response.status_code == 200, body
    assert body["dependencies"]["database"]["detail"].startswith("postgis ")
    assert body["dependencies"]["redis"] == {"ok": True, "detail": "pong"}


def test_ready_reports_unreachable_database() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://nadjet:nadjet@localhost:1/nadjet",  # type: ignore[arg-type]
        readiness_timeout_s=1.0,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["dependencies"]["database"]["ok"] is False
