#!/usr/bin/env bash
# NVIDIA Brev helpers. ALL Nadjet AI inference runs on Brev; there is no other provider.
#   scripts/brev.sh status      instance list (no secrets printed)
#   scripts/brev.sh up          start the vLLM server on the (running) instance and wait until it serves
#   scripts/brev.sh forward     localhost:$LOCAL_PORT -> instance:8000 (vLLM)
#   scripts/brev.sh unforward   stop the forward
#   scripts/brev.sh check       verify the forwarded endpoint serves the configured model
# Starting/stopping the instance itself (credits) stays manual: brev start|stop <instance>.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

INSTANCE="${NADJET_BREV_INSTANCE:-nadjet-gpu}"
LOCAL_PORT="${NADJET_VLM_LOCAL_PORT:-18000}"
REMOTE_PORT=8000
REMOTE_DIR="/home/ubuntu/nadjet-gpu"
WAIT_S="${NADJET_BREV_WAIT_S:-300}"

require_brev() {
  command -v brev >/dev/null 2>&1 || { echo "brev CLI not installed: https://docs.nvidia.com/brev/latest/" >&2; exit 1; }
  brev ls </dev/null >/dev/null 2>&1 || { echo "brev is not logged in. Run: brev login" >&2; exit 1; }
}

require_running() {
  local state
  state=$(brev ls </dev/null 2>/dev/null | awk -v n="$INSTANCE" '$1 == n {print $2}')
  if [ "$state" != "RUNNING" ]; then
    echo "Instance '$INSTANCE' is ${state:-missing}. Start it yourself (spends credits): brev start $INSTANCE" >&2
    exit 1
  fi
}

# The forward rides on Brev's multiplexed ssh connection (ControlMaster), so look for the
# local listener instead of an ssh process.
forward_listening() {
  lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1
}

case "${1:-}" in
  status)
    require_brev
    brev ls </dev/null
    ;;
  up)
    require_brev
    require_running
    brev copy deploy/gpu "$INSTANCE:$REMOTE_DIR" </dev/null >/dev/null
    brev exec "$INSTANCE" "cd $REMOTE_DIR && docker compose up -d" </dev/null 2>&1 | grep -v "waiting for SSH" || true
    echo "Waiting up to ${WAIT_S}s for vLLM to load the model..."
    deadline=$((SECONDS + WAIT_S))
    until brev exec "$INSTANCE" "curl -fsS -m 5 -o /dev/null http://localhost:$REMOTE_PORT/v1/models" </dev/null >/dev/null 2>&1; do
      [ "$SECONDS" -ge "$deadline" ] && { echo "vLLM not ready after ${WAIT_S}s. Logs: brev exec $INSTANCE 'docker logs --tail 50 nadjet-gpu-vllm-1'" >&2; exit 1; }
      sleep 10
    done
    echo "vLLM is serving on $INSTANCE:$REMOTE_PORT"
    ;;
  forward)
    require_brev
    require_running
    if forward_listening; then
      echo "Forward already listening on localhost:${LOCAL_PORT}"
    else
      # brev port-forward adds the -L forward to the background ssh connection and returns.
      brev port-forward "$INSTANCE" -p "${LOCAL_PORT}:${REMOTE_PORT}" </dev/null 2>&1 | grep -v "waiting for SSH" || true
      forward_listening && echo "Forwarding localhost:${LOCAL_PORT} -> ${INSTANCE}:${REMOTE_PORT}" ||
        { echo "Port forward did not start" >&2; exit 1; }
    fi
    ;;
  unforward)
    if ! forward_listening; then
      echo "No forward running"
      exit 0
    fi
    for host in 127.0.0.1 localhost; do
      ssh -O cancel -L "${LOCAL_PORT}:${host}:${REMOTE_PORT}" "$INSTANCE" >/dev/null 2>&1 || true
    done
    if forward_listening; then
      echo "Could not cancel the forward; stop the listener: lsof -nP -iTCP:${LOCAL_PORT} -sTCP:LISTEN" >&2
      exit 1
    fi
    echo "Forward stopped"
    ;;
  check)
    require_brev
    deadline=$((SECONDS + 60))
    until uv run nadjet-vision check-inference; do
      # A just-started server drops connections while the model loads: retry briefly.
      [ "$SECONDS" -ge "$deadline" ] && exit 1
      echo "Retrying in 10s (model may still be loading; run: make brev-up)..." >&2
      sleep 10
    done
    ;;
  *)
    echo "usage: scripts/brev.sh {status|up|forward|unforward|check}" >&2
    exit 2
    ;;
esac
