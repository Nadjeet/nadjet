# 10 — Live Stage Deployment (Dokploy VPS + NVIDIA Brev) and the No-Training Model Stack

This supersedes the "fine-tune a VideoMAE verifier" plan in docs 04 and 07. The team has no time to train, so the crash verifier is now a **pretrained open-weights VLM** (Qwen3-VL-8B). The rest of the pipeline in doc 04 is unchanged.

## 1. Models we can plug in today (no training)

| Role | Model | Licence | Hardware | Evidence | Status |
|---|---|---|---|---|---|
| Vehicle/person detection | **RF-DETR S/M** (`pip install rfdetr`), COCO | Apache-2.0 | GPU (fine on L4/L40S); CPU possible but slow | 2.3–4.4 ms/frame on T4 TRT FP16 (authors) | **Core** |
| Tracking, zones, speed | **supervision** ByteTrack + PolygonZone + ViewTransformer | MIT | CPU | Standard | **Core** |
| Candidate triggers | Our rules (doc 04 §3): overlap→both stop, hard stop not shared by traffic, stalled in live lane, person on carriageway, box aspect flip (rollover) | ours | CPU | AI City 2021 Track 4 winners used detection + tracking + rules, F1 0.95 | **Core** |
| **Crash verifier + describer** | **Qwen3-VL-8B-Instruct-FP8** via vLLM, guided JSON | Apache-2.0 | L4 24 GB (FP8) / L40S comfortable | Qwen3-VL is the base of the **CVPR 2026 ACCIDENT challenge 1st place** (frozen Qwen3-VL-32B + YOLO + tracking; code Apache-2.0): https://github.com/fuumin621/cvpr2026-accident-1st-place-solution · https://arxiv.org/abs/2605.29325 | **Core** |
| Second-opinion verifier | **Cosmos-Reason2-8B** (gated HF) | NVIDIA Open Model License | ≥ 32 GB VRAM → L40S/A100 | NVIDIA's VSS Smart-City blueprint uses it for "event verification of collisions"; NVIDIA benchmarks put it ahead of Qwen3-VL-8B on fixed-camera scenes | Optional (L40S only) |
| Smoke / fire | **D-Fire YOLOv5s** (https://github.com/pedbrgs/Fire-Detection) | weights MIT, YOLOv5 code AGPL | GPU/CPU | 21.5k-image D-Fire dataset; mAP of these weights unverified | Optional, behind a flag |
| Extra "road accident" score | `OPear/videomae-large-finetuned-UCF-Crime` | **CC-BY-NC** | GPU | 92.96% on UCF-Crime (split unclear) | Demo-only, off by default |
| Hosted fallback | Gemini Flash (video input, JSON) | commercial API | none | Used in a strong ACCIDENT pipeline (https://arxiv.org/abs/2605.01512) | **Stage fallback only.** Labelled non-sovereign |

**Rejected:**
- Roboflow "accident" YOLO models: leaky splits.
- Dashcam models such as `jatinmehra/Accident-Detection-using-Dashcam`: wrong viewpoint for fixed cameras.
- Zero-shot detectors (YOLOE, OWLv2, Grounding DINO) for "crashed car": good on nouns, weak on states. Fine for "smoke" and "person".
- NVIDIA VSS full blueprint: needs 128 GB RAM and 1–2 GPUs, takes hours to set up. **Copy its architecture and cite it**; do not deploy it.

### Verification logic

**A trigger fires.** The worker cuts a ±3 s clip and samples 8–16 frames at 448 px. It sends the frames to Qwen3-VL with a neutral prompt and a JSON schema:

```json
{"incident": true, "type": "collision|rollover|fire|stalled|pedestrian|none",
 "vehicles_involved": 2, "lanes_blocked": 1, "severity_hint": "low|medium|high",
 "description_fr": "...", "description_ar": "...", "confidence": "low|medium|high"}
```

The prompt allows `none` and says "answer only from what is visible".

**An incident becomes a `collision` only when the rule and the VLM agree.**
- If they disagree, the incident is raised as a `possible_incident` for the human to decide.
- The UI always shows three things:
  - the trigger signals (from the rules)
  - the VLM output (with its model name)
  - the operator's decision

Expected latency is about 1–3 s per check on an L40S and 3–6 s on an L4 (estimates; **measure on day 1**).

```python
# detector
from rfdetr import RFDETRMedium; det = RFDETRMedium(); dets = det.predict(frame_rgb, threshold=0.4)  # returns sv.Detections
# verifier (vLLM OpenAI-compatible, guided JSON)
client.chat.completions.create(model="Qwen/Qwen3-VL-8B-Instruct-FP8",
    messages=[{"role":"user","content":[*frames_as_image_url, {"type":"text","text":PROMPT}]}],
    extra_body={"guided_json": SCHEMA}, temperature=0)
```

### Honest failure modes (put them on the "limits" slide)

- **Missed:**
  - small, distant or night-time crashes
  - crashes occluded behind other vehicles
  - heavily compressed feeds
- **False triggers:**
  - stop-and-go traffic jams
  - merged boxes under occlusion
- **VLM errors:**
  - "sees" a crash when prompted suggestively
  - poor at pinpointing the impact time
- **Ceiling:** even the best zero-shot systems score about 0.50–0.57 on the joint time, location and type metric of the ACCIDENT benchmark.

The **human-in-the-loop** step exists because of these failure modes.

## 2. Deployment topology

```mermaid
flowchart LR
  subgraph VPS[VPS · Dokploy · Traefik TLS]
    WEB[web nginx<br/>app./respond./try.]
    API[api + arq worker<br/>api.]
    PG[(PostGIS)]
    RD[(Redis)]
    OSRM[OSRM Algeria]
    MTX[MediaMTX<br/>stream. WHEP/HLS via Traefik<br/>8554/tcp · 8189/udp+tcp published]
  end
  subgraph GPU[Brev GPU VM · L40S · docker compose]
    VLLM[vLLM Qwen3-VL-8B FP8]
    VW[vision camera x4]
    VJ[vision jobs<br/>uploads + live phones]
  end
  PHONE[Audience phones<br/>WHIP publish / upload]
  MTX -- RTSP pull :8554 --> VW & VJ
  VW & VJ -- annotated RTSP push :8554 --> MTX
  VW & VJ -- HTTPS events/jobs --> API
  VW & VJ --> VLLM
  PHONE -- WHIP --> MTX
  PHONE -- upload --> API
  WEB -- WHEP --> MTX
  API <--> PG & RD & OSRM
```

**Why this split:**
- The VPS has no GPU, and Dokploy is good at HTTP apps, databases and TLS.
- The GPU host only needs **outbound** connections:
  - pulling RTSP from the VPS
  - pushing annotated RTSP back to the VPS
  - HTTPS calls to the API

  This avoids Brev's tunnels, which go through Cloudflare and **require browser authentication on first access**, so machine-to-machine calls fail ([Brev console ref](https://docs.nvidia.com/brev/latest/guides/console-reference.md)).
- **Do not add Brev as a Dokploy remote server.** That needs public 80/443 and Dokploy's Traefik on the Brev box (unverified, risky). Plain `docker compose` on Brev is simpler and fully documented: Docker and the NVIDIA Container Toolkit are preinstalled ([Brev custom containers](https://docs.nvidia.com/brev/latest/guides/development-tools/custom-containers)).
- Video bandwidth is modest: 4 cameras × ~2 Mb/s raw + 4 × ~2 Mb/s annotated ≈ 16 Mb/s each way.

### Why annotated streams are re-encoded on the GPU (instead of drawing a canvas overlay in the browser)

- Detection boxes and video travel the same path, so they are **perfectly in sync** on stage.
- The browser stays a plain WHEP player, which is robust on any laptop or projector.
- NVENC encoding is nearly free on an L40S.
- The raw stream stays available next to it, for comparison.

## 3. VPS: Dokploy compose project `nadjet-core`

**Sizing:** at least 4 vCPU, 8 GB RAM and 60 GB disk. OSRM routing for Algeria plus PostGIS fit comfortably. Pre-process the OSRM graph offline and copy the files into the volume; do not build it on the VPS.

**Deployment mode:** use Dokploy **"Docker Compose" mode, not Stack.**
- Stack mode does not allow `build:`.
- Swarm mode handles published UDP ports and GPUs badly.
- ([Dokploy compose](https://docs.dokploy.com/docs/core/docker-compose))

```yaml
# deploy/vps/compose.yml   (images built in GitHub Actions → GHCR; Dokploy only pulls)
services:
  web:
    image: ghcr.io/nadjeet/nadjet-web:${TAG}
    expose: ["80"]
    networks: [dokploy-network]
    # domains app./respond./try./hospital. added in Dokploy UI → Traefik labels injected (redeploy after changes)

  api:
    image: ghcr.io/nadjeet/nadjet-api:${TAG}
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    env_file: .env                      # Dokploy writes compose env vars to .env only
    expose: ["8000"]
    depends_on: [db, redis]
    networks: [dokploy-network, internal]

  worker:
    image: ghcr.io/nadjeet/nadjet-api:${TAG}
    command: arq api.jobs.WorkerSettings
    env_file: .env
    networks: [internal]

  db:
    image: postgis/postgis:16-3.4
    volumes: [pgdata:/var/lib/postgresql/data]
    env_file: .env
    networks: [internal]

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redisdata:/data]
    networks: [internal]

  osrm:
    image: ghcr.io/project-osrm/osrm-backend:<pinned-tag>   # same tag used to pre-build the graph offline
    command: osrm-routed --algorithm mld /data/algeria-latest.osrm
    volumes: [osrmdata:/data]
    networks: [internal]

  mediamtx:
    image: bluenviron/mediamtx:latest-ffmpeg           # pin exact tag before stage
    volumes:
      - ../files/mediamtx.yml:/mediamtx.yml            # Dokploy File Mount
      - videos:/videos
    ports:
      - "8554:8554/tcp"      # RTSP: GPU workers pull raw / push annotated (auth required)
      - "8189:8189/udp"      # WebRTC ICE media
      - "8189:8189/tcp"      # WebRTC TCP fallback (venue Wi-Fi often blocks UDP)
    expose: ["8889", "8888", "9997"]   # WHEP/WHIP + HLS via Traefik on stream.<domain>
    networks: [dokploy-network, internal]

volumes: {pgdata: {}, redisdata: {}, osrmdata: {}, videos: {}}
networks:
  dokploy-network: {external: true}
  internal: {}
```

**Facts behind this setup** (Dokploy docs):
- Dokploy's Traefik publishes only 80/tcp and 443/tcp+udp ([manual installation](https://docs.dokploy.com/docs/core/manual-installation)).
- The extra-port UI has open bugs (Dokploy/dokploy#5509, #1479).

**Rules that follow:**
- **WebRTC media ports are published directly**; only HTTP (WHEP signalling, HLS, API) goes through Traefik.
- Open 8554/tcp and 8189/tcp+udp in the VPS firewall.
- In `mediamtx.yml`, set `webrtcAdditionalHosts: [<VPS_PUBLIC_IP>]` and `webrtcLocalTCPAddress: :8189`.
- **The `stream.` DNS record must not be behind the Cloudflare proxy.** Use DNS-only (grey cloud), because WebRTC needs the real IP.
- Lock RTSP down with MediaMTX auth:
  - `authInternalUsers` with a publish/read user for the GPU host
  - read-only WHEP for the web app
  - or delegate auth to the API with `authHTTPAddress`

**Domains (Let's Encrypt via Traefik, one certificate each; Dokploy has no documented wildcard support):**

| Domain | Points to |
|---|---|
| `app.<domain>` | web (operator) |
| `respond.<domain>` | web (responder PWA) |
| `hospital.<domain>` | web (hospital view) |
| `try.<domain>` | web (public "try it" page; this is the domain on the QR code) |
| `api.<domain>` | api |
| `stream.<domain>` | mediamtx :8889 (WHEP/WHIP) and `/hls` → :8888 |

**Secrets and backups:**
- Secrets go in Dokploy environment variables, referenced via `env_file: .env`.
- Use Dokploy volume backups to S3 for `pgdata`. Named volumes are required; bind mounts are not backed up ([backups](https://docs.dokploy.com/docs/core/databases/backups)).

## 4. Brev GPU host: `deploy/gpu/compose.yml`

**Instance:** 1× **L40S 48 GB** is recommended. It fits Qwen3-VL-8B-FP8 plus Cosmos-Reason2-8B plus the RF-DETR workers with headroom. An **L4 24 GB** works if Cosmos is dropped. Brev hourly prices were not verified; check them in the Brev console.

```yaml
x-gpu: &gpu
  deploy: {resources: {reservations: {devices: [{driver: nvidia, count: all, capabilities: [gpu]}]}}}

services:
  vllm:
    <<: *gpu
    image: vllm/vllm-openai:latest            # pin tag
    command: >
      --model Qwen/Qwen3-VL-8B-Instruct-FP8 --max-model-len 16384
      --gpu-memory-utilization 0.45 --limit-mm-per-prompt '{"image":16}'
    volumes: [hf:/root/.cache/huggingface]   # weights persist across stop/start
    env_file: .env                            # HF_TOKEN
    ports: ["127.0.0.1:8000:8000"]            # local only

  cam:
    <<: *gpu
    image: ghcr.io/nadjeet/nadjet-vision:${TAG}
    command: vision camera --all              # spawns one process per camera from cameras.yaml
    env_file: .env                            # RTSP_BASE=rtsp://gpu:***@stream.<domain>:8554, API_URL, API_TOKEN, VLM_URL=http://vllm:8000/v1
    depends_on: [vllm]
    volumes: [evidence:/evidence, hf:/root/.cache/huggingface]

  jobs:
    <<: *gpu
    image: ghcr.io/nadjeet/nadjet-vision:${TAG}
    command: vision jobs                      # long-polls https://api.<domain>/jobs/next (outbound only)
    env_file: .env
    depends_on: [vllm]

volumes: {hf: {}, evidence: {}}
```

**Brev operations** ([CLI](https://docs.nvidia.com/brev/latest/cli)):

```bash
brev create nadjet-gpu --gpu <l40s-type-from-brev-search>
brev shell nadjet-gpu
git clone https://github.com/Nadjeet/nadjet && cd nadjet/deploy/gpu && docker compose pull && docker compose up -d
```

Brev facts that drive the plan:
- Persistent data (`/home/ubuntu/workspace` and Docker images) survives a stop. `/tmp` does not.
- **A restart can fail if that GPU type is unavailable**, so **start the instance hours before the stage slot and do not stop it.**
- When credits run out, stoppable instances are paused, so top up beforehand.
- Evidence clips are uploaded to the API (and stored on a VPS volume), so the GPU box keeps no state that matters.

## 5. The "try it yourself" stage experience

| Mode | How | Why it works |
|---|---|---|
| **A. Upload a clip** (most reliable) | At `try.<domain>`, upload ≤ 60 s of video or pick one of our public sample clips. The API stores it and queues a job. `vision jobs` runs the full pipeline. The page streams progress over SSE, then shows the annotated video, the timeline of triggers, the VLM verdict and the incident created in a sandbox tenant. | Same pipeline as the cameras. The audience can bring any traffic video from their phone or YouTube. |
| **B. Your phone is a camera** (biggest wow) | Scan the QR code, open `try.<domain>/live`, and the browser publishes the camera via **WHIP** to MediaMTX (`live/<session>`). A job worker attaches to it like a CCTV feed. The phone appears **live on the stage camera wall** with AI boxes, and an incident pops up if a crash is detected. | MediaMTX accepts WHIP from browsers. Pointing a phone at a screen playing crash footage is detected less reliably (moiré, glare, shake), so mode B **forces a VLM check every 4 s** even when no rule fired. |
| **C. Operator walk-through** | A volunteer from the jury verifies the incident on the ops dashboard, dispatches, and receives the SMS on **their own phone** (number entered on the spot, deleted after the demo). | The audience is involved in the whole response chain, not just the detection. |

**Safety for public pages:**
- Rate limit per IP.
- Max 60 s / 100 MB per upload; auto-delete after 1 h.
- No storage of phone streams beyond the session.
- Consent notice in ar/fr/en.
- Sandbox tenant isolated from the "real" demo incidents.
- Hosted fallback (Gemini) only when the GPU is down, and labelled.

## 6. Stage runbook and fallbacks

**T-1 day**
- Freeze the `demo-v1` tag and deploy it on the VPS.
- Create the Brev instance, pull the images, warm vLLM.
- Run `just e2e` against production URLs.
- Record a full backup video.

**T-2 h**
- Start the camera loops and check `/system`: FPS, latency, last frame per camera.
- Send a test SMS from the gateway phone.
- Run a WHIP test from 2 different phones over 4G.

**Network**
- Bring a **dedicated 4G/5G hotspot**, and never rely on venue Wi-Fi.
- MediaMTX WebRTC TCP fallback on 8189/tcp covers networks that block UDP.
- HLS is the last resort (2–6 s latency).

**Fallback ladder**

| Problem | Fallback |
|---|---|
| GPU host down | `VLM_URL` switches to the Gemini fallback (label shown). Detection drops to the CPU RF-DETR on the laptop, which runs `deploy/local/compose.yml`. |
| VPS or internet down | Laptop **offline mode**: `deploy/local/compose.yml` runs everything plus a Mac VLM (Qwen2.5-VL-7B 4-bit via mlx-vlm). Phones join the laptop's own hotspot. |
| Everything down | Play the recorded real run and say so. |

## 7. Cost and ownership summary

| Item | Who | Cost driver |
|---|---|---|
| VPS + Dokploy + domain | Team (exists) | Fixed |
| Brev L40S during build days + stage | Team | Hourly, start/stop. Price to be checked in the console. |
| GitHub org, Actions, GHCR | Free tier for public repos | — |
| SMS | Local SIM in the gateway phone | Per SMS (operator tariff) |
| **Production** | **Government provides the GPU servers and cameras.** We ship the same compose bundles (vision node per wilaya, core in the national data centre). | Software licence and support |
