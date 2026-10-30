"""Integration: `list` against the running MediaMTX control API (`make infra-video`).

Fails (does not skip) when MediaMTX is down, so a green run means the API was reached.
"""

import time
from pathlib import Path

import httpx
import pytest
from nadjet_shared.catalogue import load_catalogue

from nadjet_camsim.control import Controller

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
API = "http://localhost:9997"


def wait_for_api(client: httpx.Client, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            client.get("/v3/paths/list").raise_for_status()
            return
        except httpx.HTTPError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def test_list_reaches_the_mediamtx_control_api() -> None:
    catalogue = load_catalogue(ROOT / "data" / "cameras.yaml")
    with httpx.Client(base_url=API, timeout=5.0) as api:
        wait_for_api(api)
        controller = Controller(
            catalogue, ROOT / "data" / "videos", api, ROOT / "deploy" / "local" / "compose.yml"
        )
        states = controller.list_states()
    assert [s.id for s in states] == [c.id for c in catalogue.cameras]
