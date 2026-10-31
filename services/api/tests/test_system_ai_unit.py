"""``GET /system/ai`` (PRD FR-VIS-009): served model id or "AI unavailable", no fallback."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient

from nadjet_api.auth.deps import current_user
from nadjet_api.auth.models import User
from nadjet_api.config import Settings
from nadjet_api.main import create_app
from nadjet_api.system.routes import AiChecker, get_ai_checker
from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import BrevVlmClient

MODEL = "Qwen/Qwen3-VL-8B-Instruct-FP8"


def served(models: list[str]) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": m} for m in models]})
    )


def refusing(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def client_for(transport: httpx.MockTransport, role: str = "operator") -> TestClient:
    app = create_app(Settings(env="test"), probes={})

    async def checker() -> AsyncIterator[AiChecker]:
        client = BrevVlmClient(VisionSettings(), transport=transport)
        try:
            yield client
        finally:
            await client.aclose()

    app.dependency_overrides[get_ai_checker] = checker
    app.dependency_overrides[current_user] = lambda: User(username="op", role=role)
    return TestClient(app)


def test_reports_the_served_model() -> None:
    with client_for(served([MODEL])) as c:
        response = c.get("/system/ai")
    assert response.status_code == 200
    assert response.json() == {"available": True, "model": MODEL, "detail": None}


def test_wrong_model_is_unavailable_not_an_error() -> None:
    with client_for(served(["other/model"])) as c:
        body = c.get("/system/ai").json()
    assert body["available"] is False
    assert body["model"] is None
    assert "other/model" in body["detail"]


def test_unreachable_endpoint_is_unavailable_without_leaking_the_address() -> None:
    with client_for(httpx.MockTransport(refusing)) as c:
        body = c.get("/system/ai").json()
    assert body == {"available": False, "model": None, "detail": "ConnectError"}


def test_http_error_from_vllm_is_unavailable() -> None:
    with client_for(httpx.MockTransport(lambda r: httpx.Response(503))) as c:
        assert c.get("/system/ai").json()["available"] is False


def test_other_roles_are_forbidden() -> None:
    with client_for(served([MODEL]), role="responder") as c:
        assert c.get("/system/ai").status_code == 403


def test_disallowed_endpoint_host_is_unavailable_without_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Brev host is refused by the client itself: still "AI unavailable", never a 500."""
    monkeypatch.setenv("NADJET_VLM_BASE_URL", "https://api.example-ai.com/v1")
    monkeypatch.setenv("NADJET_VLM_ALLOWED_HOSTS", "[]")
    app = create_app(Settings(env="test"), probes={})
    app.dependency_overrides[current_user] = lambda: User(username="op", role="operator")
    with TestClient(app) as c:
        response = c.get("/system/ai")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "example-ai" not in body["detail"]
