#!/usr/bin/env python3
"""PreToolUse guard for Bash commands (Claude Code). Enforces AGENTS.md git/Brev rules.

Reads the hook JSON on stdin. Prints a JSON decision:
- "deny"  for rule violations (co-authors, multi-line commits, force pushes, direct commits or
  pushes to dev/main, destructive git commands);
- "ask"   for actions that need the user's explicit approval (merge/close PRs, close issues,
  delete branches, Brev instance lifecycle);
- nothing (allow normal permission flow) otherwise.
"""

import json
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "dev"}
CONVENTIONAL = re.compile(
    r"^(feat|fix|refactor|perf|test|docs|build|ci|chore|revert)(\([a-z0-9-]+\))?!?: \S.{0,70}$"
)


def decide(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def current_branch(cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],  # noqa: S607 (git from PATH)
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def segments(command: str) -> list[list[str]]:
    """Split a shell command line into simple commands (on &&, ||, ;, |)."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [command.split()]
    parts: list[list[str]] = [[]]
    for tok in tokens:
        if tok and set(tok) <= set(";&|"):
            parts.append([])
        else:
            parts[-1].append(tok)
    return [p for p in parts if p]


def check_git(args: list[str], cwd: str) -> None:
    sub = args[1] if len(args) > 1 else ""
    rest = args[2:]
    if sub == "commit":
        messages = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-m", "--message")]
        messages += [a.split("=", 1)[1] for a in rest if a.startswith("--message=")]
        if any(a in ("-F", "--file") or a.startswith("--file=") for a in rest):
            decide("deny", 'Use a one-line `git commit -m "type(scope): summary"` (AGENTS.md).')
        if len(messages) != 1 or "\n" in messages[0]:
            decide(
                "deny", "Commits must be exactly one line: a single -m with no body (AGENTS.md)."
            )
        msg = messages[0]
        if re.search(r"co-authored-by|generated with|signed-off-by", msg, re.IGNORECASE):
            decide("deny", "Never add co-authors or trailers to commits (AGENTS.md).")
        if not CONVENTIONAL.match(msg):
            decide("deny", f"Not a one-line Conventional Commit (type(scope): summary): {msg!r}")
        if current_branch(cwd) in PROTECTED:
            decide("deny", "Never commit directly to dev or main: branch from origin/dev first.")
    elif sub == "push":
        if any(
            a in ("-f", "--force", "--force-with-lease", "--mirror", "--delete", "-d")
            or a.startswith(("--force", "+"))
            for a in rest
        ):
            decide(
                "deny", "Force pushes, deletes and history rewrites are not allowed (AGENTS.md)."
            )
        positional = [a for a in rest if not a.startswith("-")]
        branch = current_branch(cwd)
        refs = [a.split(":")[-1].removeprefix("refs/heads/") for a in positional[1:]] or [branch]
        if any((branch if r == "HEAD" else r) in PROTECTED for r in refs):
            decide("deny", "Never push directly to dev or main; open a PR targeting dev.")
    elif sub == "reset" and "--hard" in rest:
        decide("ask", "git reset --hard discards work. Confirm with the user first.")
    elif sub == "clean" and any(a.startswith("-") and "f" in a for a in rest):
        decide("ask", "git clean deletes untracked files. Confirm with the user first.")
    elif sub == "branch" and any(a in ("-D", "-d", "--delete") for a in rest):
        decide("ask", "Deleting a branch: verify it is the reviewed PR's head branch.")
    elif sub == "stash" and rest[:1] in (["drop"], ["clear"]):
        decide("ask", "Dropping stashes loses work. Confirm with the user first.")
    elif sub in ("checkout", "restore") and ("." in rest or "--" in rest):
        decide("ask", "This may discard working-tree changes. Confirm with the user first.")
    elif sub == "rebase" and current_branch(cwd) in PROTECTED:
        decide("deny", "Never rebase dev or main.")


def check_gh(args: list[str]) -> None:
    pair = " ".join(args[1:3])
    if pair in ("pr merge", "pr close", "issue close", "repo delete", "release delete"):
        decide(
            "ask",
            "Merging/closing requires the user's explicit confirmation that CI is green "
            "(AGENTS.md CI approval gate).",
        )


def check_brev(args: list[str]) -> None:
    if len(args) > 1 and args[1] in ("create", "delete", "start", "stop", "reset", "redeem"):
        decide("ask", "Brev instance changes spend credits or destroy state: user approval needed.")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    command = data.get("tool_input", {}).get("command", "")
    cwd = data.get("cwd") or "."
    for args in segments(command):
        while args and "=" in args[0] and not args[0].startswith("-"):
            args = args[1:]  # skip VAR=value prefixes
        if not args:
            continue
        name = args[0].rsplit("/", 1)[-1]
        if name == "git":
            check_git(args, cwd)
        elif name == "gh":
            check_gh(args)
        elif name == "brev":
            check_brev(args)
    sys.exit(0)


if __name__ == "__main__":
    main()
