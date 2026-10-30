#!/usr/bin/env bash
# Fail unless Alembic has exactly one head. Parallel PRs that each add a migration on the
# same parent create two heads; the later PR must re-point its `down_revision` to the
# current head (see .agents/rules/python-services.md). Run by `make lint` and CI.
set -euo pipefail
cd "$(dirname "$0")/../services/api"
heads=$(uv run --quiet alembic heads 2>/dev/null | grep -c "(head)" || true)
if [ "$heads" -ne 1 ]; then
  echo "FAIL: Alembic has $heads heads (expected 1):" >&2
  uv run --quiet alembic heads >&2 || true
  echo "Rebase your migration: set its down_revision to the latest revision on origin/dev." >&2
  exit 1
fi
echo "Alembic has a single head."
