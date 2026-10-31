# Demo video set: download and prepare

The simulated cameras (PRD FR-CAM-002) publish real CCTV clips from public research datasets.
The clips are **research-only: never commit or redistribute them** (`data/videos/` and `*.mp4` are
git-ignored; PRD A-01 requires us to disclose that the footage was not filmed in Algeria).
Download them by hand, accept each dataset's licence, then normalise them with `prepare.sh`.

## 1. Datasets and licences

| Dataset | Use here | Download page (check the licence there) |
|---|---|---|
| TAD (TADBench) | crash clip, stalled-vehicle clip | https://github.com/UnicomAI/UnicomBenchmark/tree/main/TADBench |
| UCF-Crime | crash clip (`RoadAccidents`), heavy-traffic clip (`Normal`) | https://www.crcv.ucf.edu/projects/real-world/ |
| CADP | evaluation pool | https://ankitshah009.github.io/accident_forecasting_traffic_camera |
| TU-DAT | evaluation pool | https://github.com/pavana27/TU-DAT |

## 2. Which clip feeds which camera

Pick clips with a fixed, roadside/overhead CCTV view. Demo clips are fixed by `data/cameras.yaml`
(`clip_id`) and must be listed in `eval/heldout.json` with `role: demo` (PRD FR-VIS-022).

| Camera id | Held-out clip id | Content |
|---|---|---|
| `cam-a1-pk42` | `demo-crash-01` | crash (TAD) |
| `cam-alg-rn5-bab-ezzouar` | `demo-crash-02` | crash at an urban crossing (team compilation, `crash-2`) |
| `cam-a1-lakhdaria` | `demo-crash-03` | night crash into a roadside pole (team compilation, `crash-1`, first 21 s) |
| `cam-alg-rocade-sud` | `demo-crash-04` | loss of control on the far carriageway (team compilation, `crash-3`) |

The three compilation clips keep their originals in `data/videos/raw/source/` (git-ignored). `crash-1`
is cut at 21 s, before the cross-fade to a later scene; nothing else is edited. Every clip starts
with several seconds of normal traffic, which is the false-positive check before each impact.

Save each download as the raw file, keeping its original container:

```
data/videos/raw/cam-a1-pk42.mp4
data/videos/raw/cam-a1-lakhdaria.mp4
data/videos/raw/cam-alg-rn5-bab-ezzouar.mp4
data/videos/raw/cam-alg-rocade-sud.mp4
data/videos/raw/eval/<any-name>.mp4        # evaluation pool, one file per clip (optional)
```

## 3. Record the clips in `eval/heldout.json`

For every clip, fill in `source_clip` (file or id inside the dataset) and, for crashes, the impact
time (`impact_time_s`) and region (`impact_region`: x, y, width, height in the 1280 px frame),
then set `annotation_status` to `annotated`. Watch the clip to annotate it; never guess. Add one
entry (`role: eval`) per clip of the evaluation pool. `make lint` validates the file
(`nadjet-camsim check`).

Held-out clips are never used to tune thresholds or prompts: no tuning code may read
`eval/heldout.json` (enforced by `scripts/check-integrity.sh`).

## 4. Normalise

```bash
brew install ffmpeg            # if missing
bash scripts/videos/prepare.sh
```

This writes `data/videos/<camera-id>.mp4` (and `data/videos/eval/*.mp4`) as H.264 baseline, 25 fps,
GOP 25, no B-frames, 1280 px wide, no audio. Frames are scaled and resampled, never edited.

## 5. Zones

`data/zones/<camera-id>.json` ships with an initial polygon set (`live_lanes`, `carriageway`) for a
1280x720 frame. After the clips are in place, open a keyframe of each camera and redraw the
polygons in image coordinates; `make lint` rejects open, empty or out-of-frame polygons.

## 6. Check the streams

```bash
make camsim && make dev          # renders the MediaMTX config and starts the cameras
make camsim-list                 # every camera should be "live"
ffplay rtsp://localhost:8554/cam-a1-pk42       # RTSP (vision workers)
open http://localhost:8889/cam-a1-pk42         # WebRTC page (browser)
```

Cameras whose video is missing are skipped by `make camsim` (a warning names them).
