import base64
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nadjet_api import cli
from nadjet_api.config import Settings


def test_serve_does_not_wait_forever_for_open_sse_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-MAP-002: a connected web client holds GET /events open; restarts must not hang on it."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))

    assert cli.main(["serve", "--port", "9000"]) == 0

    assert captured["port"] == 9000
    assert captured["timeout_graceful_shutdown"] == cli.GRACEFUL_SHUTDOWN_S


def test_gen_vapid_prints_a_usable_key_pair(capsys: pytest.CaptureFixture[str]) -> None:
    """FR-NTF-001: `nadjet-api gen-vapid` yields a P-256 key pair for Web Push."""
    assert cli.main(["gen-vapid"]) == 0

    lines = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    public = base64.urlsafe_b64decode(lines["NADJET_VAPID_PUBLIC_KEY"] + "==")
    assert len(public) == 65
    assert public[0] == 0x04  # uncompressed point, what the browser expects
    assert len(base64.urlsafe_b64decode(lines["NADJET_VAPID_PRIVATE_KEY"] + "==")) == 32


def test_send_test_sms_needs_a_configured_gateway(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(sms_gateway_url=None))

    assert cli.main(["send-test-sms", "--to", "0550123456"]) == 1
    assert "NADJET_SMS_GATEWAY_URL" in capsys.readouterr().err


def test_send_test_sms_sends_through_the_gateway(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(202, json={})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda: real_client(transport=httpx.MockTransport(handler))
    )
    settings = Settings(
        sms_gateway_url="https://gw.example",
        sms_gateway_user="u",
        sms_gateway_password=SecretStr("p"),
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert cli.main(["send-test-sms", "--to", "0550123456"]) == 0

    assert sent[0]["phoneNumbers"] == ["+213550123456"]
    assert "accepted" in capsys.readouterr().out
