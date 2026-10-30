#!/usr/bin/env bash
# NVIDIA Brev helpers. ALL Nadjet AI inference runs on Brev; there is no other provider.
#   scripts/brev.sh status      instance list (no secrets printed)
#   scripts/brev.sh forward     localhost:$LOCAL_PORT -> instance:8000 (vLLM)
#   scripts/brev.sh unforward   stop the forward
#   scripts/brev.sh check       verify the forwarded endpoint serves the configured model
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

INSTANCE="${NADJET_BREV_INSTANCE:-nadjet-gpu}"
LOCAL_PORT="${NADJET_VLM_LOCAL_PORT:-18000}"
REMOTE_PORT=8000

require_brev() {
  command -v brev >/dev/null 2>&1 || { echo "brev CLI not installed: https://docs.nvidia.com/brev/latest/" >&2; exit 1; }
  brev ls </dev/null >/dev/null 2>&1 || { echo "brev is not logged in. Run: brev login" >&2; exit 1; }
}

case "${1:-}" in
  status)
    require_brev
    brev ls </dev/null
    ;;
  forward)
    require_brev
    if pgrep -f "L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" >/dev/null; then
      echo "Forward already running on localhost:${LOCAL_PORT}"
    else
      # brev port-forward starts ssh in the background and returns.
      brev port-forward "$INSTANCE" -p "${LOCAL_PORT}:${REMOTE_PORT}" </dev/null
      echo "Forwarding localhost:${LOCAL_PORT} -> ${INSTANCE}:${REMOTE_PORT}"
    fi
    ;;
  unforward)
    pkill -f "L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" && echo "Forward stopped" || echo "No forward running"
    ;;
  check)
    require_brev
    uv run nadjet-vision check-inference
    ;;
  *)
    echo "usage: scripts/brev.sh {status|forward|unforward|check}" >&2
    exit 2
    ;;
esac
