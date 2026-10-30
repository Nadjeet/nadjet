"""Tests for the agent guard hook (.claude/hooks/guard_bash.py) and the git commit-msg hook."""

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / ".claude" / "hooks" / "guard_bash.py"
COMMIT_MSG = ROOT / ".githooks" / "commit-msg"


def load(path: Path, name: str) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


commit_msg = load(COMMIT_MSG, "commit_msg_hook")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "feat/1-x")
    return tmp_path


def run_guard(command: str, cwd: Path) -> dict[str, str] | None:
    payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
    out = subprocess.run(
        [sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, check=True
    )
    if not out.stdout.strip():
        return None
    result: dict[str, str] = json.loads(out.stdout)["hookSpecificOutput"]
    return result


def decision(command: str, cwd: Path) -> str:
    result = run_guard(command, cwd)
    return result["permissionDecision"] if result else "allow"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "feat(api): add inbound sms parser"',
        "git status && git diff",
        "git push -u origin HEAD",
        "gh pr view 12 --json title",
        "make test",
    ],
)
def test_normal_workflow_commands_are_allowed(command: str, repo: Path) -> None:
    assert decision(command, repo) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "feat: x" -m "body"',
        'git commit -m "feat(api): x\n\nCo-Authored-By: Claude <noreply@anthropic.com>"',
        'git commit -m "Add stuff"',
        "git commit -F msg.txt",
        "git push --force origin feat/1-x",
        "git push -f",
        "git push origin dev",
        "git push origin HEAD:main",
        'cd x && git commit -m "fix(api): Co-authored-by someone"',
    ],
)
def test_rule_violations_are_denied(command: str, repo: Path) -> None:
    assert decision(command, repo) == "deny"


def test_commit_and_push_on_protected_branch_are_denied(repo: Path) -> None:
    subprocess.run(["git", "switch", "-q", "-c", "dev"], cwd=repo, check=True)
    assert decision('git commit -m "fix(api): x"', repo) == "deny"
    assert decision("git push", repo) == "deny"
    assert decision("git push origin HEAD", repo) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 12 --rebase --delete-branch",
        "gh pr close 12",
        "gh issue close 7",
        "git branch -D feat/1-x",
        "git reset --hard origin/dev",
        "brev create my-gpu",
        "brev delete nadjet-gpu",
    ],
)
def test_actions_needing_user_approval_ask(command: str, repo: Path) -> None:
    assert decision(command, repo) == "ask"


@pytest.mark.parametrize(
    "message",
    ["feat(api): add sms parser", "fix: handle empty payload", "docs(prd): bump to v0.6"],
)
def test_commit_msg_accepts_one_line_conventional(message: str) -> None:
    assert commit_msg.validate(message + "\n") is None


@pytest.mark.parametrize(
    "message",
    [
        "Add sms parser",
        "feat(api): add parser\n\nlonger body",
        "feat(api): add parser\n\nCo-Authored-By: X <x@y.z>",
        "feat(API): uppercase scope",
        "feat(api): " + "x" * 80,
        "",
    ],
)
def test_commit_msg_rejects_invalid(message: str) -> None:
    assert commit_msg.validate(message) is not None


def test_commit_msg_ignores_git_comments() -> None:
    assert commit_msg.validate("fix(web): align header\n# Please enter the message\n") is None
