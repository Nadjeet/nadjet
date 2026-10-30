"""scripts/brev.sh tunnel commands, run against fake ``brev`` and ``ssh`` binaries (issue #7)."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

FAKE_BREV = """#!/usr/bin/env bash
echo "brev $*" >> "$FAKE_LOG"
[ "$1" = "ls" ] && echo "nadjet-gpu $FAKE_STATE"
exit 0
"""
# `ss` checks on the instance report "nothing listening" (exit 1); everything else succeeds.
FAKE_SSH = """#!/usr/bin/env bash
echo "ssh $*" >> "$FAKE_LOG"
case "$*" in *"ss -ltn"*) exit 1 ;; esac
exit 0
"""


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """Copy of the script in a folder without .env, plus fake binaries."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "brev.sh", tmp_path / "scripts" / "brev.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("brev", FAKE_BREV), ("ssh", FAKE_SSH)):
        path = bin_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run(sandbox: Path, command: str, state: str = "RUNNING") -> tuple[int, str, str]:
    log = sandbox / "calls.log"
    env = {
        **os.environ,
        "PATH": f"{sandbox / 'bin'}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "FAKE_STATE": state,
        "NADJET_VLM_LOCAL_PORT": "48999",  # nothing listens here
    }
    done = subprocess.run(
        ["bash", str(sandbox / "scripts" / "brev.sh"), command],
        capture_output=True,
        text=True,
        env=env,
        cwd=sandbox,
        check=False,
    )
    return done.returncode, done.stderr, log.read_text() if log.exists() else ""


def test_tunnel_refuses_when_instance_is_not_running_and_never_starts_it(sandbox: Path) -> None:
    code, err, calls = run(sandbox, "tunnel", state="STOPPED")
    assert code == 1
    assert "brev start nadjet-gpu" in err
    assert "brev start" not in calls
    assert "brev stop" not in calls
    assert "ssh " not in calls


def test_tunnel_opens_vllm_local_forward_and_two_remote_forwards(sandbox: Path) -> None:
    code, _, calls = run(sandbox, "tunnel")
    assert code == 0
    assert "ssh -O forward -L 48999:127.0.0.1:8000 nadjet-gpu" in calls
    assert "ssh -O forward -R 18554:127.0.0.1:8554 nadjet-gpu" in calls
    assert "ssh -O forward -R 18080:127.0.0.1:8080 nadjet-gpu" in calls


def test_untunnel_cancels_all_three_forwards(sandbox: Path) -> None:
    code, _, calls = run(sandbox, "untunnel")
    assert code == 0
    assert "ssh -O cancel -L 48999:127.0.0.1:8000 nadjet-gpu" in calls
    assert "ssh -O cancel -R 18554:127.0.0.1:8554 nadjet-gpu" in calls
    assert "ssh -O cancel -R 18080:127.0.0.1:8080 nadjet-gpu" in calls


def test_deploy_workers_and_logs_refuse_when_instance_is_stopped(sandbox: Path) -> None:
    for command in ("deploy-workers", "logs"):
        code, err, calls = run(sandbox, command, state="STOPPED")
        assert code == 1
        assert "brev start nadjet-gpu" in err
        assert "brev copy" not in calls
        assert "brev exec" not in calls
