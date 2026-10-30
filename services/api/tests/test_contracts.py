from pathlib import Path

from nadjet_api.cli import DEFAULT_OPENAPI, export_openapi, render_openapi


def test_openapi_lists_system_endpoints() -> None:
    assert '"/health"' in render_openapi()
    assert '"/ready"' in render_openapi()


def test_export_check_detects_drift(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    assert export_openapi(target, check=True) == 1
    assert not target.exists()
    assert export_openapi(target, check=False) == 0
    assert export_openapi(target, check=True) == 0


def test_committed_openapi_is_up_to_date() -> None:
    assert export_openapi(DEFAULT_OPENAPI, check=True) == 0
