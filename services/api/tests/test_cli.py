from typing import Any

import pytest

from nadjet_api import cli


def test_serve_does_not_wait_forever_for_open_sse_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-MAP-002: a connected web client holds GET /events open; restarts must not hang on it."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))

    assert cli.main(["serve", "--port", "9000"]) == 0

    assert captured["port"] == 9000
    assert captured["timeout_graceful_shutdown"] == cli.GRACEFUL_SHUTDOWN_S
