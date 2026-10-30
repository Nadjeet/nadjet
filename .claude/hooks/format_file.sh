#!/usr/bin/env bash
# PostToolUse (Edit|Write): format the edited file with the repo formatter. Never blocks.
set -uo pipefail
file=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
case "$file" in
  */node_modules/* | */.venv/* | */contracts/* | */schema.d.ts | */.agents/skills/* | */.claude/skills/*) exit 0 ;;
  *.py) uv run --quiet ruff format --quiet "$file" >/dev/null 2>&1 ;;
  *.ts | *.tsx | *.css | *.json | *.html | *.yml | *.yaml)
    pnpm exec prettier --write --log-level silent "$file" >/dev/null 2>&1 ;;
esac
exit 0
