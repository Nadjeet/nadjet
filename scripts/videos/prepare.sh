#!/usr/bin/env bash
# Normalise downloaded research clips into streamable simulator videos (PRD FR-CAM-002).
#
#   data/videos/raw/<camera-id>.<ext>   ->  data/videos/<camera-id>.mp4        (demo cameras)
#   data/videos/raw/eval/<name>.<ext>   ->  data/videos/eval/<name>.mp4        (evaluation pool)
#
# H.264 baseline, 25 fps, GOP 25 (1 s keyframes), no B-frames, 1280 px wide, no audio: safe for
# `ffmpeg -c copy` publishing and WebRTC. Frames are only scaled/resampled, never edited.
# Re-run with FORCE=1 to re-encode existing outputs. See scripts/videos/fetch.md.
set -euo pipefail
cd "$(dirname "$0")/../.."

command -v ffmpeg >/dev/null || { echo "ffmpeg is required (brew install ffmpeg)" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe is required (brew install ffmpeg)" >&2; exit 1; }

raw=data/videos/raw
out=data/videos
[ -d "$raw" ] || { echo "No $raw directory: download the clips first (scripts/videos/fetch.md)." >&2; exit 1; }

normalise() { # <input> <output>
  local in=$1 dst=$2
  if [ -f "$dst" ] && [ -z "${FORCE:-}" ] && [ "$dst" -nt "$in" ]; then
    echo "up to date  $dst"
    return
  fi
  mkdir -p "$(dirname "$dst")"
  ffmpeg -hide_banner -loglevel error -y -i "$in" -an \
    -vf "scale=1280:-2,fps=25" \
    -c:v libx264 -preset veryfast -profile:v baseline -pix_fmt yuv420p \
    -g 25 -keyint_min 25 -sc_threshold 0 -bf 0 -movflags +faststart "$dst"
  verify "$dst"
  echo "prepared    $dst"
}

verify() { # fail loudly if the output is not what the simulator needs
  local info
  info=$(ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,profile,r_frame_rate,width -of csv=p=0 "$1")
  case "$info" in
    h264,Constrained\ Baseline,1280,25/1 | h264,Baseline,1280,25/1) ;;
    *) echo "unexpected stream in $1: $info" >&2; exit 1 ;;
  esac
}

count=0
for f in "$raw"/*; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  normalise "$f" "$out/${name%.*}.mp4"
  count=$((count + 1))
done
if [ -d "$raw/eval" ]; then
  for f in "$raw"/eval/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    normalise "$f" "$out/eval/${name%.*}.mp4"
    count=$((count + 1))
  done
fi
[ "$count" -gt 0 ] || { echo "No clips found in $raw (see scripts/videos/fetch.md)." >&2; exit 1; }

echo "Done: $count clip(s). Next: make camsim && make dev (or make infra-video)."
