#!/usr/bin/env bash
# Validate the local development environment. Used by `make doctor` and `make setup`.
# Exit 1 if a required tool is missing; warnings never fail.
set -uo pipefail

cd "$(dirname "$0")/.."
fail=0
ok() { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
warn() { printf "  \033[33mWARN\033[0m %s\n" "$1"; }
bad() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; fail=1; }

need() { # name, version-command, hint
  if command -v "$1" >/dev/null 2>&1; then ok "$1 $($2 2>/dev/null | head -1)"; else bad "$1 missing — $3"; fi
}

echo "Required tools"
need git "git --version" "https://git-scm.com"
need uv "uv --version" "curl -LsSf https://astral.sh/uv/install.sh | sh"
need node "node --version" "install Node >= 22 (see .nvmrc)"
need pnpm "pnpm --version" "corepack enable && corepack prepare pnpm@10 --activate"
need docker "docker --version" "install Docker Desktop / Engine"
need make "make --version" "install GNU make"

if command -v node >/dev/null 2>&1; then
  major=$(node -p 'process.versions.node.split(".")[0]')
  [ "$major" -ge 22 ] && ok "node major $major >= 22" || bad "node $major < 22"
fi
if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 && ok "docker daemon running" || bad "docker daemon not running"
  docker compose version >/dev/null 2>&1 && ok "docker compose plugin" || bad "docker compose plugin missing"
fi

echo "Workflow tools"
if command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null 2>&1 && ok "gh authenticated" || warn "gh not authenticated — run: gh auth login"
else
  warn "gh missing — needed for /implement-issue and /review-pr (https://cli.github.com)"
fi
command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg (video prep)" || warn "ffmpeg missing — only needed to prepare demo videos"

echo "AI inference (NVIDIA Brev only)"
if command -v brev >/dev/null 2>&1; then
  ok "brev $(brev --no-check-latest --version 2>/dev/null | head -1 | sed 's/Current Version: //')"
  if brev ls </dev/null >/dev/null 2>&1; then ok "brev logged in"; else warn "brev not logged in — run: brev login"; fi
else
  warn "brev missing — AI features need it (https://docs.nvidia.com/brev/latest/)"
fi

echo "Project files"
[ -f .env ] && ok ".env present" || warn ".env missing — run: make setup (copies .env.example)"
[ -d .venv ] && ok "Python environment (.venv)" || warn ".venv missing — run: make setup"
[ -d node_modules ] && ok "Node modules" || warn "node_modules missing — run: make setup"
videos=$(find data/videos -maxdepth 1 -name '*.mp4' 2>/dev/null | wc -l | tr -d ' ')
[ "$videos" -gt 0 ] && ok "$videos demo video(s) in data/videos" || warn "no demo videos in data/videos (cameras will be skipped)"

exit $fail
