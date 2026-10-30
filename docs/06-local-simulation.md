# 06 — Local Simulation Strategy (real pipeline, no faked results)

## 1. Rules of honesty (non-negotiable)

1. **No hardcoded events.** No incident may be created from a timestamp table, a file name or a "demo mode" flag. Every camera incident must come from the vision pipeline processing the decoded frames.
2. **No fabricated confidence.** Each confidence value shown must be the model's output or a documented rule score. The UI shows its source.
3. **Demo clips are held out** from all training and threshold tuning. `data/splits.json` lists them, and a CI check verifies that the training scripts never read them.
4. **We disclose the limits on the slide.**
   - The footage is public research CCTV and was not filmed in Algeria.
   - The virtual cameras are *geotagged* to real Algerian road locations.
5. **We show failures as well.** The demo includes a heavy-traffic clip with no alert, and the evaluation page reports false alarms per camera-hour.

## 2. Virtual camera network

### Camera catalogue (`sim/cameras.yaml`)

```yaml
cameras:
  - id: cam-a1-pk42
    name: "A1 East-West Hwy – Khemis El Khechna PK42 (westbound)"
    video: videos/heldout/tad_0153_h264.mp4      # contains a crash (held-out)
    geo: { lat: 36.6480, lon: 3.3290 }           # approximate, see note
    road: A1
    pk_km: 42
    heading_deg: 270
    wilaya: Boumerdès
    zones: zones/cam-a1-pk42.json                # live lanes, shoulder, carriageway polygons
  - id: cam-a1-lakhdaria
    video: videos/heldout/normal_heavy_traffic_h264.mp4   # congestion, should NOT alert
  - id: cam-alg-rn5-bab-ezzouar
    video: videos/heldout/ucf_roadacc_0xx_h264.mp4
  - id: cam-alg-rocade-sud
    video: videos/heldout/stalled_vehicle_h264.mp4
```

- **Location choice.** The Khemis El Khechna–Lakhdaria section of the A1 in Boumerdès is a documented deadly section (El Watan, January 2025), and Boumerdès opened a 387-camera surveillance centre in 2026. That makes it a credible demo setting.
- **Coordinates are approximate.** Pick them on the map and label them as simulated camera positions.

### Video preparation

```bash
# Normalise every clip to H.264 baseline, 1 s GOP, no B-frames: safe for -c copy and WebRTC
ffmpeg -i in.mp4 -vf "scale=1280:-2,fps=25" -c:v libx264 -preset veryfast -profile:v baseline \
  -g 25 -keyint_min 25 -bf 0 -an out_h264.mp4
```

- Many research clips are short (10–60 s) and low resolution.
- For a believable live feed, **concatenate** normal traffic from the same camera before the incident segment where available. Otherwise loop the clip.
- Never edit the frames themselves.

### MediaMTX configuration (`sim/mediamtx.yml`, generated from `cameras.yaml`)

```yaml
rtspAddress: :8554
webrtcAddress: :8889
hlsAddress: :8888
api: yes
webrtcAdditionalHosts: [192.168.1.20]   # LAN IP so phones on the Wi-Fi can watch
paths:
  cam-a1-pk42:
    runOnInit: ffmpeg -re -stream_loop -1 -i videos/heldout/tad_0153_h264.mp4 -c copy -f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH
    runOnInitRestart: yes
  # ... one path per camera
```

**Native run on macOS:**

```bash
brew install mediamtx ffmpeg
mediamtx sim/mediamtx.yml
```

Each camera is then available at:
- `rtsp://localhost:8554/<id>` for the vision worker
- `http://localhost:8889/<id>/whep` for the browser

### Simulator control CLI (`sim/camctl.py`)

| Command | Effect | Mechanism |
|---|---|---|
| `camctl list` | Shows cameras, publisher PIDs and readers | MediaMTX API `/v3/paths/list` |
| `camctl restart <cam>` | Restarts the clip from 0 | Kills ffmpeg; MediaMTX restarts it through `runOnInitRestart` |
| `camctl freeze <cam>` / `unfreeze` | Frozen feed while the session stays open | `SIGSTOP` / `SIGCONT` on the ffmpeg PID |
| `camctl outage <cam>` | Camera offline | Kill the publisher and disable the path through the API |
| `camctl swap <cam> <video>` | Plays a different clip | Rewrite the path through the API (`PATCH /v3/config/paths/patch/<cam>`) |

- The freeze and outage commands exercise feature **A4, camera health**: the worker detects a stale PTS or a missing stream and raises `camera_fault`.
- `restart` and `swap` are **operator conveniences, not event injection**. The pipeline still has to detect what is in the video.

## 3. Real processing path

```
MediaMTX (RTSP) → vision worker (PyAV decode, 5–10 fps sampling)
  → detector (RF-DETR) → ByteTrack → relative speed → zone tests
  → triggers + AI sweep → AI verifier (Qwen3-VL-8B, no training) → status → candidate
  → evidence: encoded-packet ring buffer (15 s pre) + 10 s post → MP4 + 6 keyframes + SHA-256
  → Redis XADD incidents.candidates
  → API: dedupe (same camera ±60 s & ±50 m) → priority → DB → SSE
```

**Loop deduplication.** A looped clip re-triggers the same crash. The API merges candidates from the same camera and location inside a cooldown window, so the crash appears once. It also counts "re-observed" events, which is honest.

**Zones (one-off per camera, a few minutes).** Draw the live-lane and carriageway polygons on a keyframe and store them as JSON. No metric calibration is needed: speed is measured relative to vehicle size (doc 11 TD-03). Metric calibration is only for real production cameras.

## 4. Authority and responder simulation (real software, real delivery)

| Actor | What we run | Real or simulated |
|---|---|---|
| Civil Protection unit, Gendarmerie patrol | Responder PWA on 1–2 real phones + SMS to a real phone | **Real delivery** |
| Civil Protection operations room / DGSN centre | Operator dashboard on the laptop / projector | Real software |
| Hospital emergency department (e.g. CHU Mustapha, EPH Rouiba) | Hospital pre-alert view on a tablet + SMS | Real software; the hospital data is simulated |
| Citizen | Report page on a phone + SMS keyword | Real |
| SMS network | Android phone with a local SIM running **capcom6 SMS Gateway** in local-server mode | **Real SMS** |
| Telegram channel (optional) | Bot posting alerts to a "Wilaya Ops" group | Real |
| Facilities | OSM hospitals / fire_station / police for Boumerdès and Algiers, plus a seeded `facilities.csv` (capabilities, SMS numbers = team phones) | **Facility locations are real. Capabilities and contacts are simulated (labelled).** |
| Units | 6–10 seeded units with home stations; position updates when a responder app reports GPS | Simulated fleet |

**SMS gateway test:**

```bash
curl -u $GW_USER:$GW_PASS -H 'Content-Type: application/json' http://$PHONE_IP:8080/message \
  -d '{"textMessage":{"text":"ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3"},"phoneNumbers":["+2135XXXXXXXX"]}'
```

- Check the request field name against https://docs.sms-gate.app for the installed version.
- Inbound SMS reaches the API through the gateway's webhook (`sms:received` → `POST /sms/inbound`).

## 5. Data and assets checklist

| Asset | Source | Use |
|---|---|---|
| Accident CCTV clips | TAD (UnicomBenchmark/TADBench), CADP, TU-DAT, UCF-Crime RoadAccidents | Train/validate the verifier (train split); demo (held-out split) |
| Normal / jam CCTV | UCF-Crime Normal, TAD negatives, AI City (if access) | Hard negatives; false-alarm evaluation |
| Detector weights | `yolo11s.pt` → CoreML | Vehicle / person detection |
| Verifier weights | `Qwen/Qwen3-VL-8B-Instruct-FP8` (pretrained, no fine-tuning) | Crash verification and AI sweep |
| VLM | Served by vLLM on NVIDIA Brev (`deploy/gpu/compose.yml`), reached with `make brev-forward` | Verification and AI sweep |
| Map tiles | `pmtiles extract https://build.protomaps.com/<date>.pmtiles algeria.pmtiles --bbox=-8.7,18.9,12.0,37.2` | Offline basemap |
| Routing graph | Geofabrik `algeria-latest.osm.pbf` → OSRM MLD | ETA, routes |
| Facilities | Overpass query (`amenity=hospital|clinic|fire_station|police`, `emergency=ambulance_station`) in DZ | Unit/hospital recommendation |

**Licences.** The datasets are research-only and the clips are not redistributed. The repo ships download scripts (`data/fetch.sh`), not the videos.

## 6. One-command bring-up

```bash
make setup       # tools check, uv + pnpm dependencies, git hooks, .env
make dev         # PostGIS, Redis, MediaMTX (simulated cameras), API, web
make brev-forward && make brev-check   # AI inference on NVIDIA Brev (only provider)
make test        # unit + integration tests (no frontend tests)
```

**Health page** `/system` shows the following, so the jury can see the real pipeline running:
- camera FPS
- inference latency per stage
- queue depths
- last frame timestamp per camera
