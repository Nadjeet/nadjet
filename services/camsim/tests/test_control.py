"""Simulator controls: MediaMTX API calls and docker exec commands (PRD FR-CAM-004)."""

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from nadjet_camsim.cli import main
from nadjet_camsim.control import ControlError, Controller, compose_exec, signal_command
from nadjet_shared.catalogue import Catalogue

CAMERA = {
    "id": "cam-a1-pk42",
    "name": "A1 PK42",
    "video": "crash.mp4",
    "clip_id": "demo-crash-01",
    "geo": {"lat": 36.648, "lon": 3.329},
    "road": "A1",
    "wilaya": "Boumerdès",
}
COMPOSE = Path("deploy/local/compose.yml")


class Recorder:
    """Fake MediaMTX API + docker runner that records every call."""

    def __init__(self, paths: list[dict[str, object]] | None = None, returncode: int = 0) -> None:
        self.requests: list[httpx.Request] = []
        self.commands: list[list[str]] = []
        self.paths = paths or []
        self.returncode = returncode

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v3/paths/list":
            return httpx.Response(200, json={"items": self.paths})
        return httpx.Response(200, json={})

    def run(self, argv: list[str]) -> "subprocess.CompletedProcess[str]":
        self.commands.append(argv)
        return subprocess.CompletedProcess(argv, self.returncode, "", "")

    def controller(self, videos: Path) -> Controller:
        api = httpx.Client(base_url="http://mtx:9997", transport=httpx.MockTransport(self.handler))
        return Controller(
            Catalogue.model_validate({"cameras": [CAMERA]}), videos, api, COMPOSE, run=self.run
        )


@pytest.fixture
def videos(tmp_path: Path) -> Path:
    (tmp_path / "crash.mp4").write_bytes(b"\x00")
    (tmp_path / "other.mp4").write_bytes(b"\x00")
    return tmp_path


def test_signal_command_matches_only_the_publisher_of_that_camera() -> None:
    assert signal_command("STOP", "cam-a1-pk42") == "pkill -STOP -f '[f]fmpeg .*/cam-a1-pk42$'"


def test_compose_exec_targets_the_mediamtx_service() -> None:
    argv = compose_exec(COMPOSE, "mediamtx", "true")
    assert argv[:2] == ["docker", "compose"]
    assert argv[argv.index("exec") + 1 :] == ["-T", "mediamtx", "sh", "-c", "true"]


@pytest.mark.parametrize(
    ("command", "signal"),
    [("freeze", "STOP"), ("unfreeze", "CONT"), ("restart", "KILL")],
)
def test_signal_commands_exec_in_the_container(videos: Path, command: str, signal: str) -> None:
    rec = Recorder()
    getattr(rec.controller(videos), command)("cam-a1-pk42")
    assert rec.requests == []  # no API call: the RTSP session must stay as it is
    assert rec.commands[0][-1] == signal_command(signal, "cam-a1-pk42")


def test_freeze_fails_clearly_when_no_publisher_runs(videos: Path) -> None:
    with pytest.raises(ControlError, match="no running publisher"):
        Recorder(returncode=1).controller(videos).freeze("cam-a1-pk42")


def test_outage_deletes_the_path_and_kills_a_lingering_publisher(videos: Path) -> None:
    rec = Recorder(returncode=1)  # kill finding nothing is fine
    rec.controller(videos).outage("cam-a1-pk42")
    assert (rec.requests[0].method, rec.requests[0].url.path) == (
        "DELETE",
        "/v3/config/paths/delete/cam-a1-pk42",
    )
    assert rec.commands[0][-1] == signal_command("KILL", "cam-a1-pk42")


def test_restore_adds_the_catalogue_clip(videos: Path) -> None:
    rec = Recorder()
    rec.controller(videos).restore("cam-a1-pk42")
    request = rec.requests[0]
    assert (request.method, request.url.path) == ("POST", "/v3/config/paths/add/cam-a1-pk42")
    assert "/videos/crash.mp4" in json.loads(request.content)["runOnInit"]


def test_swap_patches_the_path_with_the_new_clip(videos: Path) -> None:
    rec = Recorder()
    rec.controller(videos).swap("cam-a1-pk42", "other.mp4")
    request = rec.requests[0]
    assert (request.method, request.url.path) == ("PATCH", "/v3/config/paths/patch/cam-a1-pk42")
    body = json.loads(request.content)
    assert "/videos/other.mp4" in body["runOnInit"]
    assert body["runOnInitRestart"] is True


@pytest.mark.parametrize("video", ["../crash.mp4", "/etc/passwd", "missing.mp4", "x;rm.mp4"])
def test_swap_rejects_paths_and_missing_files(videos: Path, video: str) -> None:
    rec = Recorder()
    with pytest.raises(ControlError):
        rec.controller(videos).swap("cam-a1-pk42", video)
    assert rec.requests == []


def test_unknown_camera_is_rejected(videos: Path) -> None:
    with pytest.raises(ControlError, match="unknown camera"):
        Recorder().controller(videos).freeze("nope")


def test_list_reports_live_and_offline_cameras(videos: Path) -> None:
    live = {"name": "cam-a1-pk42", "ready": True, "source": {"type": "rtspSource"}, "readers": [{}]}
    [state] = Recorder([live]).controller(videos).list_states()
    assert (state.online, state.readers) == (True, 1)
    [state] = Recorder([]).controller(videos).list_states()
    assert state.online is False


def test_api_errors_are_reported(videos: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="path already exists")

    api = httpx.Client(base_url="http://mtx:9997", transport=httpx.MockTransport(refuse))
    controller = Controller(Catalogue.model_validate({"cameras": [CAMERA]}), videos, api, COMPOSE)
    with pytest.raises(ControlError, match="400: path already exists"):
        controller.restore("cam-a1-pk42")


def test_unreachable_api_suggests_make_dev(videos: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    api = httpx.Client(base_url="http://mtx:9997", transport=httpx.MockTransport(down))
    controller = Controller(Catalogue.model_validate({"cameras": [CAMERA]}), videos, api, COMPOSE)
    with pytest.raises(ControlError, match="make dev"):
        controller.list_states()


def test_check_command_validates_repository_data(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    assert "Catalogue OK" in capsys.readouterr().out


def test_cli_reports_control_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["freeze", "nope", "--api", "http://127.0.0.1:1"], run=Recorder().run)
    assert code == 1
    assert "unknown camera" in capsys.readouterr().err


def test_docker_failure_is_not_reported_as_missing_publisher(videos: Path) -> None:
    recorder = Recorder(returncode=1)
    recorder.run = lambda argv: subprocess.CompletedProcess(  # type: ignore[method-assign]
        argv, 125, "", "Cannot connect to the Docker daemon"
    )
    with pytest.raises(ControlError, match="Docker daemon"):
        recorder.controller(videos).freeze("cam-a1-pk42")


def test_missing_docker_binary_is_a_control_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from nadjet_camsim import control

    def boom(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(control.subprocess, "run", boom)
    with pytest.raises(ControlError, match="is Docker installed"):
        control.run_subprocess(["docker", "ps"])
