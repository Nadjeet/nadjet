"""Unit: citizen report validation that needs no database (FR-CIT-001, FR-CIT-004)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nadjet_api.citizen.routes import PHONE_RE, limit_reports, photo_type
from nadjet_api.db import get_session
from nadjet_api.incidents.deps import get_redis
from nadjet_api.main import create_app

from .conftest import make_settings


def app_without_infra(tmp_path: Path, **settings: object) -> FastAPI:
    """Validation runs before the database or Redis are used: stub their dependencies."""
    app = create_app(make_settings(tmp_path, **settings), probes={})
    for dependency in (limit_reports, get_redis, get_session):
        app.dependency_overrides[dependency] = lambda: None
    return app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(app_without_infra(tmp_path)) as c:
        yield c


def test_photo_type_reads_the_bytes_not_the_client_header() -> None:
    assert photo_type(b"\xff\xd8\xff\xe0abcd") == ("image/jpeg", ".jpg")
    assert photo_type(b"\x89PNG\r\n\x1a\n") == ("image/png", ".png")
    assert photo_type(b"GIF89a..") is None
    assert photo_type(b"") is None


@pytest.mark.parametrize("phone", ["0550123456", "+213 550 12 34 56", "00213550123456"])
def test_phone_accepts_algerian_formats(phone: str) -> None:
    assert PHONE_RE.match(phone)


@pytest.mark.parametrize("phone", ["abc", "12", "0550-123-456; DROP", "+" * 12])
def test_phone_rejects_garbage(phone: str) -> None:
    assert PHONE_RE.match(phone) is None


@pytest.mark.parametrize(
    "form",
    [
        {"lat": "48.85", "lon": "2.35"},  # Paris: outside Algeria
        {"lat": "36.7", "lon": "3.1", "people_reported": "100"},
        {"lat": "36.7", "lon": "3.1", "people_reported": "-1"},
        {"lat": "36.7", "lon": "3.1", "phone": "not a phone"},
        {"lat": "abc", "lon": "3.1"},
        {"lon": "3.1"},
    ],
)
def test_invalid_report_is_rejected_before_any_state_change(
    client: TestClient, form: dict[str, str]
) -> None:
    assert client.post("/public/reports", data=form).status_code == 422


def test_non_image_photo_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/public/reports",
        data={"lat": "36.7", "lon": "3.1"},
        files={"photo": ("x.jpg", b"%PDF-1.7 not an image", "image/jpeg")},
    )
    assert response.status_code == 415


def test_oversized_photo_is_rejected(tmp_path: Path) -> None:
    with TestClient(app_without_infra(tmp_path, public_photo_max_mb=1)) as c:
        response = c.post(
            "/public/reports",
            data={"lat": "36.7", "lon": "3.1"},
            files={"photo": ("x.jpg", b"\xff\xd8\xff" + b"0" * (1024 * 1024), "image/jpeg")},
        )
    assert response.status_code == 413
