#!/usr/bin/env bash
# Repository integrity rules (AGENTS.md). Run by `make lint` and CI.
#  1. No fabricated AI results: no random values in service/package source code (PRD FR-VIS-020).
#  2. AI inference only on NVIDIA Brev: no other AI provider endpoints or SDKs.
#  3. No frontend test files (testing policy).
set -uo pipefail
cd "$(dirname "$0")/.."
status=0

src_dirs="services/*/src packages/shared/src"

if grep -rnE '^\s*(import random|from random import)|\brandom\.(random|uniform|randint|choice)\(' $src_dirs; then
  echo "FAIL: random values in source code (fabricated results are forbidden)." >&2
  status=1
fi

providers='api\.openai\.com|generativelanguage\.googleapis\.com|api\.anthropic\.com|integrate\.api\.nvidia\.com|build\.nvidia\.com|api\.groq\.com|api\.together\.xyz|openrouter\.ai|^\s*(import|from) (openai|anthropic|google\.genai|google\.generativeai)\b'
if grep -rnE "$providers" $src_dirs apps/web/src packages/api-client/src; then
  echo "FAIL: AI provider other than NVIDIA Brev referenced in code." >&2
  status=1
fi

if find apps packages/api-client -path '*/node_modules' -prune -o \
  \( -name '*.test.*' -o -name '*.spec.*' -o -name '__tests__' -o -name 'playwright.config.*' -o -name 'vitest.config.*' -o -name 'cypress' \) -print | grep .; then
  echo "FAIL: frontend tests are not allowed (AGENTS.md testing policy)." >&2
  status=1
fi

# Held-out demo clips are never used for tuning (PRD FR-VIS-022): only the catalogue validators
# and the published evaluation script may mention the held-out list.
heldout_readers='^(packages/shared/src/nadjet_shared/(heldout|catalogue)\.py|services/camsim/src/nadjet_camsim/cli\.py|eval/run_eval\.py):'
if grep -rnIE 'held-?out(\.json)?' $src_dirs apps/web/src scripts/videos eval --include='*.py' --include='*.ts' --include='*.tsx' --include='*.sh' --include='*.json' 2>/dev/null |
  grep -vE "$heldout_readers"; then
  echo "FAIL: only the catalogue validators and eval/run_eval.py may reference the held-out list (FR-VIS-022)." >&2
  status=1
fi

[ $status -eq 0 ] && echo "Integrity checks passed."
exit $status
