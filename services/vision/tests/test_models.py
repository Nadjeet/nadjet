"""models.lock.yaml: pinned, permissive, verified before use (TD-25, NFR-LIC-001)."""

import hashlib
from pathlib import Path

import httpx
import pytest

from nadjet_vision.models import (
    ModelEntry,
    ModelWeightError,
    ensure_weights,
    licence_violations,
    load_lock,
    verify_weights,
)

ROOT = Path(__file__).resolve().parents[3]
BLOB = b"weights"


def entry(sha: str | None = None, **extra: object) -> ModelEntry:
    return ModelEntry(
        id="m",
        role="detector",
        source="https://example.test/m.pth",
        filename="m.pth",
        sha256=sha or hashlib.sha256(BLOB).hexdigest(),
        licence="Apache-2.0",
        **extra,  # type: ignore[arg-type]
    )


def test_repo_lock_pins_a_permissive_default_detector() -> None:
    lock = load_lock(ROOT / "models.lock.yaml")
    detector = lock["rf-detr-medium"]
    assert detector.default
    assert len(detector.sha256) == 64
    assert licence_violations(lock) == []


def test_agpl_model_enabled_by_default_is_a_violation() -> None:
    bad = entry(default=True).model_copy(update={"licence": "AGPL-3.0"})
    assert licence_violations({"m": bad}) == ["m"]
    assert licence_violations({"m": bad.model_copy(update={"default": False})}) == []


def test_verify_rejects_a_changed_file(tmp_path: Path) -> None:
    path = tmp_path / "m.pth"
    path.write_bytes(b"tampered")
    with pytest.raises(ModelWeightError, match="checksum mismatch"):
        verify_weights(path, entry())


def test_ensure_downloads_once_and_verifies(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=BLOB)

    transport = httpx.MockTransport(handler)
    first = ensure_weights(entry(), tmp_path / "w", transport)
    second = ensure_weights(entry(), tmp_path / "w", transport)
    assert first == second
    assert first.read_bytes() == BLOB
    assert len(calls) == 1


def test_ensure_discards_a_download_with_the_wrong_checksum(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"other"))
    with pytest.raises(ModelWeightError):
        ensure_weights(entry(), tmp_path, transport)
    assert list(tmp_path.iterdir()) == []
