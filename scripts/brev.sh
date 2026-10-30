#!/usr/bin/env bash
# NVIDIA Brev helpers. ALL Nadjet AI inference runs on Brev; there is no other provider.
#   scripts/brev.sh status      instance list (no secrets printed)
#   scripts/brev.sh up          start the vLLM server on the (running) instance and wait until it serves
#   scripts/brev.sh forward     localhost:$LOCAL_PORT -> instance:8000 (vLLM)
#   scripts/brev.sh unforward   stop the forward
#   scripts/brev.sh check       verify the forwarded endpoint serves the configured model
#   scripts/brev.sh tunnel      vLLM to local (-L) and local MediaMTX + API to the instance (-R)
#   scripts/brev.sh untunnel    cancel all three forwards
#   scripts/brev.sh deploy-workers   pull (or build on the instance) the vision image, start workers
#   scripts/brev.sh logs [-f]   vision worker logs from the instance
# Starting/stopping the instance itself (credits) stays manual: brev start|stop <instance>.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

INSTANCE="${NADJET_BREV_INSTANCE:-nadjet-gpu}"
LOCAL_PORT="${NADJET_VLM_LOCAL_PORT:-18000}"
REMOTE_PORT=8000
REMOTE_DIR="/home/ubuntu/nadjet-gpu"
REMOTE_SRC="/home/ubuntu/nadjet-src"   # build context when the image is built on the instance
RTSP_LOCAL_PORT="${NADJET_RTSP_LOCAL_PORT:-8554}"   # local MediaMTX RTSP
API_LOCAL_PORT="${NADJET_API_LOCAL_PORT:-8080}"     # local API
RTSP_REMOTE_PORT="${NADJET_RTSP_REMOTE_PORT:-18554}" # seen from the instance
API_REMOTE_PORT="${NADJET_API_REMOTE_PORT:-18080}"
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

# Does something listen on this port ON the instance? (rides the multiplexed ssh connection)
remote_listening() {
  ssh "$INSTANCE" "ss -ltn | grep -q ':$1 '" </dev/null >/dev/null 2>&1
}

# Run a command on the instance, hide Brev's connection noise and fail if the command failed.
# A sentinel is used because `brev exec` does not reliably return the remote exit status.
remote_ok() {
  local out
  out=$(brev exec "$INSTANCE" "$1 && echo NADJET_REMOTE_OK" </dev/null 2>&1 || true)
  printf '%s\n' "$out" | grep -v -e "waiting for SSH" -e "NADJET_REMOTE_OK" || true
  printf '%s\n' "$out" | grep -q "NADJET_REMOTE_OK"
}

# Open the Brev ssh master connection if it is not up yet (port-forward starts one).
ensure_master() {
  ssh -O check "$INSTANCE" </dev/null >/dev/null 2>&1 && return 0
  brev port-forward "$INSTANCE" -p "${LOCAL_PORT}:${REMOTE_PORT}" </dev/null 2>&1 | grep -v "waiting for SSH" || true
  ssh -O check "$INSTANCE" </dev/null >/dev/null 2>&1 || { echo "No ssh connection to $INSTANCE" >&2; exit 1; }
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
    brev exec "$INSTANCE" "cd $REMOTE_DIR && docker compose up -d vllm" </dev/null 2>&1 | grep -v "waiting for SSH" || true
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
  tunnel)
    require_brev
    require_running
    ensure_master
    if ! forward_listening; then
      ssh -O forward -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$INSTANCE" </dev/null
    fi
    if ! remote_listening "$RTSP_REMOTE_PORT"; then
      ssh -O forward -R "${RTSP_REMOTE_PORT}:127.0.0.1:${RTSP_LOCAL_PORT}" "$INSTANCE" </dev/null
    fi
    if ! remote_listening "$API_REMOTE_PORT"; then
      ssh -O forward -R "${API_REMOTE_PORT}:127.0.0.1:${API_LOCAL_PORT}" "$INSTANCE" </dev/null
    fi
    echo "localhost:${LOCAL_PORT} -> ${INSTANCE}:${REMOTE_PORT} (vLLM)"
    echo "${INSTANCE}:${RTSP_REMOTE_PORT} -> localhost:${RTSP_LOCAL_PORT} (MediaMTX RTSP)"
    echo "${INSTANCE}:${API_REMOTE_PORT} -> localhost:${API_LOCAL_PORT} (API)"
    ;;
  untunnel)
    for host in 127.0.0.1 localhost; do
      ssh -O cancel -L "${LOCAL_PORT}:${host}:${REMOTE_PORT}" "$INSTANCE" </dev/null >/dev/null 2>&1 || true
    done
    ssh -O cancel -R "${RTSP_REMOTE_PORT}:127.0.0.1:${RTSP_LOCAL_PORT}" "$INSTANCE" </dev/null >/dev/null 2>&1 || true
    ssh -O cancel -R "${API_REMOTE_PORT}:127.0.0.1:${API_LOCAL_PORT}" "$INSTANCE" </dev/null >/dev/null 2>&1 || true
    if forward_listening; then
      echo "Local forward on ${LOCAL_PORT} still listening: lsof -nP -iTCP:${LOCAL_PORT} -sTCP:LISTEN" >&2
      exit 1
    fi
    if ssh -O check "$INSTANCE" </dev/null >/dev/null 2>&1 &&
      { remote_listening "$RTSP_REMOTE_PORT" || remote_listening "$API_REMOTE_PORT"; }; then
      echo "A remote forward is still listening on the instance (${RTSP_REMOTE_PORT}/${API_REMOTE_PORT})" >&2
      exit 1
    fi
    echo "Tunnels closed"
    ;;
  deploy-workers)
    require_brev
    require_running
    brev copy deploy/gpu "$INSTANCE:$REMOTE_DIR" </dev/null >/dev/null
    # Secrets travel in a 0600 env file on the instance, never on a command line or in logs.
    envfile=$(mktemp)
    trap 'rm -f "$envfile"' EXIT
    { echo "NADJET_INGEST_TOKEN=${NADJET_INGEST_TOKEN:-}"
      echo "NADJET_VLM_MODEL=${NADJET_VLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct-FP8}"
      echo "NADJET_BUILD_CONTEXT=$REMOTE_SRC"
      [ -n "${NADJET_VISION_IMAGE:-}" ] && echo "NADJET_VISION_IMAGE=$NADJET_VISION_IMAGE"
    } >"$envfile"
    brev copy "$envfile" "$INSTANCE:$REMOTE_DIR/.env" </dev/null >/dev/null
    brev exec "$INSTANCE" "chmod 600 $REMOTE_DIR/.env" </dev/null >/dev/null 2>&1
    image="${NADJET_VISION_IMAGE:-ghcr.io/nadjeet/nadjet-vision:dev}"
    # Pull, then check the image really is there: a failed pull (private GHCR package without
    # `docker login ghcr.io` on the instance) must fall back to a build, not to a broken `up`.
    if remote_ok "cd $REMOTE_DIR && docker compose --profile workers pull workers >/dev/null 2>&1 && docker image inspect $image >/dev/null"; then
      echo "Pulled $image from the registry"
    else
      echo "Could not pull $image (not published yet, or private: run 'docker login ghcr.io' on the instance). Building on the instance"
      tarball=$(mktemp)
      git archive --format=tar.gz -o "$tarball" HEAD pyproject.toml uv.lock models.lock.yaml packages services data/cameras.yaml data/zones .dockerignore
      brev copy "$tarball" "$INSTANCE:/home/ubuntu/nadjet-src.tgz" </dev/null >/dev/null
      rm -f "$tarball"
      remote_ok "rm -rf $REMOTE_SRC && mkdir -p $REMOTE_SRC && tar -xzf /home/ubuntu/nadjet-src.tgz -C $REMOTE_SRC && cd $REMOTE_DIR && docker compose --profile workers build workers" \
        || { echo "Building the vision image on the instance failed (see above)" >&2; exit 1; }
    fi
    remote_ok "cd $REMOTE_DIR && docker compose --profile workers up -d" \
      || { echo "Starting the workers failed (see above)" >&2; exit 1; }
    echo "Workers started (from the committed HEAD, not uncommitted changes). Logs: make brev-logs"
    ;;
  logs)
    require_brev
    require_running
    follow=""
    [ "${2:-}" = "-f" ] && follow="-f"
    brev exec "$INSTANCE" "cd $REMOTE_DIR && docker compose --profile workers logs --tail 100 $follow workers" </dev/null
    ;;
  *)
    echo "usage: scripts/brev.sh {status|up|forward|unforward|check|tunnel|untunnel|deploy-workers|logs}" >&2
    exit 2
    ;;
esac
