#!/usr/bin/env bash
# Build the offline Algeria basemap: extract a bbox from a Protomaps daily build into
# data/map/algeria.pmtiles (git-ignored). Needs Docker and internet once; ~1-3 GB, a few minutes.
set -euo pipefail
cd "$(dirname "$0")/.."

PMTILES_IMAGE="protomaps/go-pmtiles:v1.31.2"
BBOX="${NADJET_MAP_BBOX:-"-8.7,18.9,12.0,37.2"}" # Algeria; override for a smaller local area
MAXZOOM="${NADJET_MAP_MAXZOOM:-14}"
OUT_DIR="data/map"

build=""
for days_ago in 1 2 3 4 5 6 7; do
  day=$(date -u -d "$days_ago days ago" +%Y%m%d 2>/dev/null || date -u -v-"${days_ago}"d +%Y%m%d)
  if curl -fsI "https://build.protomaps.com/${day}.pmtiles" >/dev/null; then
    build="$day"
    break
  fi
done
[ -n "$build" ] || { echo "No Protomaps daily build found in the last 7 days." >&2; exit 1; }

mkdir -p "$OUT_DIR"
echo "Extracting Protomaps build $build (bbox $BBOX, maxzoom $MAXZOOM)..."
rm -f "$OUT_DIR/algeria.pmtiles" # a failed run leaves a partial file
for attempt in 1 2 3 4; do # the public build server drops long transfers now and then
  if docker run --rm -v "$PWD/$OUT_DIR:/data" "$PMTILES_IMAGE" \
    extract "https://build.protomaps.com/${build}.pmtiles" /data/algeria.pmtiles \
    --bbox="$BBOX" --maxzoom="$MAXZOOM"; then
    ls -lh "$OUT_DIR/algeria.pmtiles"
    exit 0
  fi
  echo "Extract failed (attempt $attempt/4), retrying..." >&2
  rm -f "$OUT_DIR/algeria.pmtiles"
done
exit 1
