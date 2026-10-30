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
    assert detector.sha256 is not None and len(detector.sha256) == 64
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


def test_repo_lock_pins_the_served_verifier_by_revision_and_licence() -> None:
    lock = load_lock(ROOT / "models.lock.yaml")
    verifier = lock["qwen3-vl-8b-instruct-fp8"]
    assert (verifier.role, verifier.default, verifier.served_by) == ("verifier", True, "vllm")
    assert verifier.revision is not None and len(verifier.revision) == 40
    assert verifier.licence == "Apache-2.0"
    # The served model is the one the worker is configured for (compose and settings agree).
    assert verifier.source.endswith("Qwen/Qwen3-VL-8B-Instruct-FP8")


def test_the_lock_names_exactly_one_default_per_role_and_all_are_permissive() -> None:
    lock = load_lock(ROOT / "models.lock.yaml")
    defaults = [e.role for e in lock.values() if e.default]
    assert sorted(defaults) == ["detector", "verifier"]
    assert licence_violations(lock) == []


def test_a_served_model_needs_a_revision_and_a_downloaded_one_needs_a_checksum() -> None:
    with pytest.raises(ValueError, match="pinned revision"):
        ModelEntry(
            id="v", role="verifier", source="https://x", licence="Apache-2.0", served_by="vllm"
        )
    with pytest.raises(ValueError, match="filename and sha256"):
        ModelEntry(id="d", role="detector", source="https://x", licence="Apache-2.0")


def test_nothing_is_downloaded_for_a_served_model(tmp_path: Path) -> None:
    served = ModelEntry(
        id="v", role="verifier", source="https://x", licence="Apache-2.0",
        served_by="vllm", revision="a" * 40,
    )  # fmt: skip
    with pytest.raises(ModelWeightError, match="nothing to download"):
        ensure_weights(served, tmp_path)
