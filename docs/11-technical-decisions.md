# 11 — Technical Decisions Register (the "how" behind the PRD)

The [PRD](../PRD.md) describes **what** Nadjet must do and **why**. It is deliberately technology-neutral (PRD decision D-13). This document records **how** we implement it today: models, frameworks, services and deployment.

**Change rule:**

- If a technology changes, update this register (add a new `TD-` row and mark the old one superseded). Do **not** edit the PRD.
- Edit the PRD only if a change alters what the product does, a requirement, a success criterion or a product constraint.

Supporting detail lives in:

- [04 AI feasibility](04-ai-feasibility.md)
- [05 Architecture & stack](05-architecture-and-stack.md)
- [06 Local simulation](06-local-simulation.md)
- [09 Repositories & stack](09-repositories-and-stack.md)
- [10 Live deployment & models](10-live-deployment-and-models.md)

If those documents disagree with this register, **this register wins**.

---

## 1. Technical decisions

| ID | Date | Decision | Alternatives rejected | Rationale | Serves (PRD) |
|---|---|---|---|---|---|
| TD-01 | 2026-10-30 | **AI verifier:** pretrained **Qwen3-VL-8B-Instruct-FP8** (Apache-2.0) on **vLLM**, used for both the verifier and the sweep. Input sent as **one video**: 16 dense frames at 4 fps around the moment (±2 s) plus 4 context frames (−8 s to +4 s), 768 px, **timestamp drawn on each frame**. Structured JSON, temperature 0, **no thinking mode**, neutral question that allows "no collision". Confidence = probability of the yes/no answer token (logprobs), not self-reported confidence | Fine-tuned VideoMAE (needs training); Cosmos-Reason2 (lost to Qwen3-VL in the ACCIDENT 1st-place tests, missed T-bone crashes, slow reasoning); Qwen3-VL-32B (small gain, does not fit next to the rest on one L40S) | No training (PRD C-02). Settings follow the CVPR 2026 ACCIDENT winners: 4 fps beat 10 fps, thinking mode collapsed timing, overlays of tracking trails hurt. Video input halves visual tokens vs image lists | FR-VIS-005, FR-VIS-007, FR-VIS-015, D-03 |
| TD-02 | 2026-10-30 | **Detector:** **RF-DETR** (Apache-2.0), COCO classes | Ultralytics YOLO11/26 (AGPL-3.0) | Permissive licence for a government product (PRD NFR-LIC-001); real-time on GPU | FR-VIS-002 |
| TD-03 | 2026-10-30 | **Tracking, zones, speed:** `supervision` (MIT): ByteTrack + PolygonZone. **Speed = pixel displacement divided by box height, smoothed over 0.5–1 s** (no calibration). Homography (ViewTransformer) only for calibrated production cameras | Homography on every demo camera (public clips have unknown geometry; speed is very sensitive to calibration errors, Revaud et al. ICCV 2021); Ultralytics track mode (AGPL) | Rules only need relative speed changes | FR-VIS-003, FR-VIS-004 |
| TD-04 | 2026-10-30 | **Optional modules:** smoke/fire detector (`weslleyskah/fire_smoke_box` YOLO26n or D-Fire YOLOv5s; both AGPL-derived), run as a **separate process**, off by default in production, may be enabled for the public hackathon demo | Cosmos-Reason2 second opinion (dropped); `OPear` VideoMAE UCF-Crime (CC-BY-NC, dropped); person-exit counting and thermal person detection (dropped for the MVP, D-16) | Keep the core path licence-clean and the scope small | FR-VIS-012, D-06, D-16 |
| TD-05 | 2026-10-30 | **One monorepo** `Nadjeet/nadjet`, plus `Nadjeet/.github` for the org profile | Polyrepo | Shared contracts change atomically; easier for agents; Dokploy watch paths; GitHub path-filtered builds | NFR-MAINT-001 |
| TD-06 | 2026-10-30 | **Video server:** **MediaMTX** (MIT). RTSP/WHIP in; WebRTC (WHEP) and LL-HLS out. Simulator = ffmpeg `-re -stream_loop -1 -c copy` via `runOnInit` | go2rtc; GStreamer; WebCodecs over WebSocket | One binary covers simulated cameras, annotated republish, phone-as-camera and browser playback | FR-CAM-001..004, FR-CIT-003, SC-007 |
| TD-07 | 2026-10-30 | **Annotated stream:** re-encoded on the GPU (NVENC) and republished to the video server | Canvas overlay in the browser | Boxes and video stay in perfect sync on stage; the browser is a plain player | FR-VIS-008 |
| TD-08 | 2026-10-30 | **Backend:** Python 3.12, **FastAPI**, Pydantic v2, SQLAlchemy 2 + Alembic, arq jobs | NestJS, Go | Same language as the AI workers; generated OpenAPI spec | FR-INC, FR-DSP, FR-NTF |
| TD-09 | 2026-10-30 | **Data:** PostgreSQL + **PostGIS**; **Redis Streams** for candidates and jobs | TimescaleDB, Kafka, NATS | Geospatial nearest-unit queries; durable queue with replay at low operational cost | FR-DSP-001, NFR-REL-002 |
| TD-10 | 2026-10-30 | **Routing:** self-hosted **OSRM** on the Geofabrik Algeria extract. Facilities seeded once from Overpass, plus a CSV | Valhalla, GraphHopper, hosted APIs | Fastest car ETA; offline; free | FR-DSP-001..004 |
| TD-11 | 2026-10-30 | **Frontend:** one **Vite + React 19 + TypeScript** SPA with 4 surfaces; TanStack Router/Query; Tailwind + shadcn/ui; MapLibre GL + self-hosted Protomaps PMTiles; vite-plugin-pwa; i18next (ar/fr/en, RTL) | Next.js; 4 separate apps; Leaflet; hosted tiles | Static build, smallest deploy; team's strongest stack; offline sovereign map | FR-MAP, FR-RSP, FR-HSP, FR-CIT |
| TD-12 | 2026-10-30 | **Real-time to browsers:** SSE for incident updates; WebSocket where interactive | Polling | Auto-reconnecting push | FR-MAP-002, NFR-PERF-002 |
| TD-13 | 2026-10-30 | **SMS:** **SMS Gateway for Android** (capcom6, Apache-2.0) on our own phone and SIM, in **private-server mode** (gateway server self-hosted on the VPS). Cloud mode (`api.sms-gate.app`) is the backup. **Local mode only for the offline laptop fallback** | Twilio (needs a card; no two-way SMS in Algeria; Mobilis rejects numeric sender IDs); local mode on stage (the internet VPS cannot reach a phone behind NAT) | Free, no card, real two-way SMS, sovereign | FR-NTF-003, D-08 |
| TD-14 | 2026-10-30 | **Other channels:** Web Push (VAPID, no account); Telegram Bot API | Firebase-only push | Free, no card | FR-NTF-001 |
| TD-15 | 2026-10-30 | **Alert format:** OASIS **CAP 1.2** XML, validated against the XSD | Custom JSON only | Standard for civil-protection systems | FR-INC-009, NFR-COMP-001 |
| TD-16 | 2026-10-30 | **Evidence integrity:** SHA-256 per file; hash chain over incident events; **Ed25519**-signed chain head (PyNaCl) | — | Tamper-evident and verifiable | FR-SEC-003 |
| TD-17 | 2026-10-30 | **Stage deployment:** **VPS + Dokploy** in Docker Compose mode (not Stack) runs web, api, worker, PostGIS, Redis, OSRM and MediaMTX. Traefik + Let's Encrypt for HTTP. WebRTC/RTSP ports (8189 udp+tcp, 8554 tcp) published directly. `stream.` DNS must not go through the Cloudflare proxy | Brev as a Dokploy remote server; Swarm mode | Dokploy's Traefik only proxies HTTP; Swarm handles UDP and GPUs badly | NFR-FLEX-001 |
| TD-18 | 2026-10-30 | **GPU host:** **NVIDIA Brev**, 1× L40S (L4 as fallback). Budget: $90 of credits, plan about 28 h (≈ $30–52), see doc 10 §4. Plain `docker compose` running vLLM and the vision workers. **Outbound connections only** (RTSP pull/push to the VPS, HTTPS to the API) | Brev tunnels (they require browser authentication); hosted inference APIs as the main path | Simple, documented, no inbound ports | NFR-PERF-001, NFR-PERF-003 |
| TD-19 | 2026-10-30 | **CI/CD:** GitHub Actions builds images and pushes them to **GHCR** (`ghcr.io/nadjeet/nadjet-{web,api,vision}`). Dokploy only pulls. Stage pins to the tag `demo-v1` | Building on the VPS | CUDA images are 5–15 GB; Dokploy re-clones on every deploy | NFR-MAINT-001 |
| TD-20 | 2026-10-30 | ~~Hosted AI fallback (Gemini)~~ **Superseded by TD-27** | — | — | — |
| TD-21 | 2026-10-30 | **Offline fallback:** `deploy/local` runs the full stack on the laptop **except AI inference** (Brev only, TD-27) | Local Mac VLM (superseded by TD-27) | Stage resilience | NFR-REL-003 |
| TD-22 | 2026-10-30 | **AI sweep:** every 5 s per camera, the last 8 s at 2 fps, 640 px, sent as one video to the same Qwen3-VL server. Threshold on the yes-token probability. Sweep-only detections are at most `probable` | Sentinel every 10–15 s (too slow for SC-001); no sweep (rules miss crashes) | Rule-based detection alone reached 71% detection in published work and had about twice the timing error of the VLM (arXiv 1911.10037, 2605.01512). NVIDIA RT-VLM handles dozens of streams per GPU | FR-VIS-015 |
| TD-23 | 2026-10-30 | **Upload two-pass:** pass 1 scans the whole clip at 1–2 fps with a "no collision" option; pass 2 looks at ±2–3 s around the found time at 4 fps; correction damped and capped; RF-DETR only snaps the result onto vehicles | Rules on uploads (break on unseen camera angles) | Same method as all three ACCIDENT 2026 top papers | FR-CIT-002 |
| TD-24 | 2026-10-30 | **Validation layer:** Pydantic schema check; every finding must cite an existing frame ID, else dropped and logged; trilingual (AR/FR/EN) safety-word filter; one retry with the validation error, then a template description from rule signals | Trusting raw VLM text | Prevents hallucinated or harmful wording reaching operators | FR-VIS-016, FR-VIS-017 |
| TD-25 | 2026-10-30 | **`models.lock.yaml`:** every weight pinned with source, version, checksum and licence; CI fails if an AGPL or non-commercial model is enabled by default in a production profile. `VLM_MODE=mock` (recorded answers) allowed only in `tests/`; production start-up refuses it | — | Licence hygiene and no fake AI outside tests | NFR-LIC-001, FR-VIS-020 |
| TD-26 | 2026-10-30 | **Task runner: GNU `make`** (`Makefile`, works with make 3.81 on macOS). `make help` lists everything | `just` (extra install) | Zero-install, universal | NFR-MAINT-001 |
| TD-27 | 2026-10-30 | **NVIDIA Brev is the only AI inference provider**, including local development: `make brev-forward` (localhost:18000 → instance:8000), `make brev-check`. `BrevVlmClient` refuses non-loopback hosts unless listed in `NADJET_VLM_ALLOWED_HOSTS`; `scripts/check-integrity.sh` fails CI on other provider endpoints/SDKs | Gemini fallback (TD-20), Mac mlx-vlm (TD-21) | One sovereign path, no silent fallbacks (PRD D-17) | FR-VIS-009, FR-CIT-005, NFR-PRIV-002 |
| TD-28 | 2026-10-30 | **Testing policy:** pytest unit + integration tests for every non-frontend component (integration = real PostGIS/Redis, fail when infra is down); `@pytest.mark.brev` live checks never in CI; **no frontend tests of any kind** (enforced by `scripts/check-integrity.sh`) | Vitest/Playwright for the web app | Effort on business logic and contracts | NFR-MAINT-001 |
| TD-29 | 2026-10-30 | **Contracts source of truth = code:** Pydantic models in `packages/shared` and FastAPI routes; `make gen` exports `contracts/events/*.schema.json`, `contracts/openapi.json` and the TS client (`openapi-typescript` + `openapi-fetch`); CI fails on drift | Hand-written JSON Schemas + `datamodel-code-generator` | One definition, type-checked | NFR-MAINT-001 |
| TD-30 | 2026-10-30 | **Local infra:** `imresamu/postgis:17-3.5` (multi-arch: arm64 Macs + amd64 CI), `redis:8-alpine`, `bluenviron/mediamtx:1.21.2-ffmpeg`; host ports 55432 / 56379 to avoid clashes; API 8080, web 5173 | `postgis/postgis` (amd64 only) | Works on every dev machine and in CI | — |
| TD-31 | 2026-10-30 | **Agent workflow:** `AGENTS.md` single source; `/implement-issue` (Sonnet 5.5) and `/review-pr` (Opus 5.5) skills in `.agents/skills/` linked into `.claude/skills/`; guard hooks + git hooks enforce one-line Conventional Commits, no co-authors, no direct pushes to `dev`/`main`; PRs target `dev` | — | Standardised issue-to-PR lifecycle | — |
| TD-32 | 2026-10-30 | **Auth:** `argon2-cffi` (Argon2id) passwords, `PyJWT` HS256 access tokens (`NADJET_JWT_SECRET`, refused in production if weak), `PyYAML` for `seed-users`. Audit log = append-only via DB triggers (UPDATE/DELETE/TRUNCATE rejected) + SHA-256 hash chain serialised by a Postgres advisory lock. Rate limiter = Redis fixed window per client IP | `pwdlib`, OAuth2 password form, DB roles/grants only | Small, maintained, no extra services; triggers work for the table owner too | FR-SEC-001, FR-SEC-004, NFR-SEC-002, FR-CIT-004 |
| TD-33 | 2026-10-30 | **Incident engine:** candidates go API → Redis Stream `incidents.candidates` (consumer group `api`, ack after DB commit, stale entries re-claimed with `XAUTOCLAIM`, malformed ones dead-lettered); persistence idempotent on the candidate key (unique `incident_events.idempotency_key`). Merge = `ST_DWithin` on geography (50 m) + 60 s against the incident's latest candidate time. Per-incident event chain (same hash rule as `audit_log`), every head signed with Ed25519 (PyNaCl, `NADJET_SIGNING_KEY`); `incident_events` append-only by trigger. Short codes derived by hash (deterministic, unique among open incidents via partial index). SSE over Redis Pub/Sub carrying ids only, filtered by scope. `python-multipart` for evidence upload | Polling the DB; random short codes; `sse-starlette`; GeoAlchemy2 (geom is a DB-generated column) | No candidate lost (NFR-REL-002), tamper-evident evidence (FR-SEC-003), small payloads scoped per role | FR-INC-001..008, FR-SEC-003/004, NFR-REL-002, NFR-PERF-002 |
| TD-34 | 2026-10-30 | **Web foundation:** code-based TanStack Router (role guards in `beforeLoad`), TanStack Query over `@nadjet/api-client` with a bearer middleware; live events read through the same client with `parseAs: "stream"` and a small SSE parser (an `EventSource` cannot send the `Authorization` header), reconnect with jittered back-off and a 35 s silence watchdog; shadcn/ui (radix) restyled to the Nadjet Figma design system with the Figma purple replaced by the brand blue; DM Sans + Noto Sans Arabic via Fontsource; lucide icons; `vite-plugin-pwa` 2 (manifest + precache service worker); `nadjet-api serve` caps graceful shutdown so open event streams do not block restarts | `EventSource` with a token query param (token in URLs and logs); `@microsoft/fetch-event-source`; file-based routing plugin; `openapi-react-query` | No new server code, no token in URLs, fewer dependencies; one palette for all surfaces | FR-MAP-002, FR-MAP-005, FR-RSP-005, NFR-INT-001, NFR-INT-002, FR-VIS-021 |
| TD-35 | 2026-10-30 | **Camera registry and simulator controls:** catalogue, zones and held-out models live in `nadjet_shared` (read by camsim and the API). `cameras.geom` is a PostGIS column generated from `lat`/`lon` (no geoalchemy2). Outage, restore and swap use the MediaMTX control API (`DELETE`/`POST`/`PATCH /v3/config/paths/...`); freeze, unfreeze and restart signal the ffmpeg publisher with `docker compose exec` + `pkill`. `httpx` added to camsim. `seed-cameras` upserts and never deletes | geoalchemy2; freezing through the API (MediaMTX cannot pause a source) | No new heavy dependency; a stopped ffmpeg keeps the RTSP session open, which the freeze test (US-13) needs | FR-CAM-001, FR-CAM-004, FR-VIS-022, FR-ADM-001 |
| TD-36 | 2026-10-30 | **Vision runtime on Brev (dev):** one image `services/vision/Dockerfile` (CUDA 12.4 runtime, Python 3.12 via uv, `nadjet-vision[gpu]`, apt ffmpeg with `NVIDIA_DRIVER_CAPABILITIES=…,video` for NVENC), built for `linux/amd64` and pushed to `ghcr.io/nadjeet/nadjet-vision:{sha,branch}` by a CI job on `dev`/`main` pushes only. The `workers` service in `deploy/gpu/compose.yml` uses `network_mode: host`. In development the instance reaches the laptop over the Brev ssh alias with `ssh -O forward -R` (RTSP 18554, API 18080) next to `-L 18000` for vLLM; outbound-only production (TD-18) is unchanged. Instance start/stop stays manual | `brev port-forward` (only `-L`); inbound ports on the GPU host; building the image locally and pushing from laptops | Reuses the multiplexed ssh connection `scripts/brev.sh` already relies on; workers need no public endpoint; no registry login on laptops | NFR-PERF-001, NFR-MAINT-001 |
| TD-37 | 2026-10-30 | **Vision worker pipeline:** one process per camera, started by a supervisor (`nadjet-vision camera --all`, restart back-off 1 s to 30 s). Ingest is PyAV over RTSP/TCP, sampled at 5 fps by PTS into a 2-slot latest-frame queue; the last 15 s of encoded packets are kept in a ring that always starts on a keyframe. Detection is `RFDETRMedium` behind a `Detector` protocol (weights pinned by SHA-256 in `models.lock.yaml`, downloaded once, verified before load). Tracking is ByteTrack from the Roboflow `trackers` package (Apache-2.0; `supervision` 0.31 dropped its tracker); **zone membership is a plain point-in-polygon on the box's ground point** and relative speed is the median of per-step displacement divided by box height over 1 s; global camera motion is **FFT phase correlation** of small grey frames (no OpenCV needed, 2 of 3 frames above 2 px). The annotated stream is drawn with OpenCV and piped to ffmpeg `h264_nvenc` as `<camera>_ai` at the analysis rate (5 fps). Each worker pushes a `CameraHealthReport` every 5 s to `POST /internal/camera-health` (latest report in Redis, TTL 60 s; stale after 15 s) and serves Prometheus text on `/metrics`. **Fault = no analysed frame for 10 s**; the reason (`stall` if the stream is open, `disconnect` if not) sticks until a frame arrives. A fault sets `cameras.status = degraded` once and publishes `camera_fault` / `camera_recovered` on the live channel | `PolygonZone` (needs OpenCV masks, no gain for single-point tests); optical flow for camera motion; one multi-camera process (one crash would stop all) | Keeps detection logic testable on CI without GPU packages; one failing camera cannot stop the others; fault timing stays inside the 15 s of US-13 | FR-VIS-001, FR-VIS-002, FR-VIS-003, FR-VIS-008, FR-VIS-011, FR-CAM-005, NFR-REL-001, NFR-PERF-001 |

---

## 2. External services in use (PRD constraint C-01: free, no credit card)

The team already owns: an NVIDIA Brev account, a VPS with Dokploy, and a domain name. Everything below was verified on 2026-10-30.

| Need | Service | Card? | Limits and caveats | Source |
|---|---|---|---|---|
| Code, CI, images | GitHub Free org, Actions, GHCR | No | Unlimited standard runners and free GHCR for **public** repos | https://docs.github.com/en/billing/concepts/product-billing/github-actions · https://docs.github.com/en/billing/concepts/product-billing/github-packages |
| Model weights | Hugging Face Hub (free token) | No | 5,000 file requests per 5 min with a token. No gated model in the core path | https://huggingface.co/docs/hub/rate-limits |
| TLS | Let's Encrypt via Traefik | No | 50 certificates per domain per week; test against staging | https://letsencrypt.org/docs/rate-limits/ |
| Push | Web Push (VAPID) | No account | iOS requires the PWA on the home screen (16.4+) | https://webkit.org/blog/12945/meet-web-push/ |
| Chat alerts | Telegram Bot API | No | About 20 messages/min per group | https://core.telegram.org/bots/faq |
| SMS | SMS Gateway for Android (capcom6) | No account | **Our SIM pays the operator tariff** (PRD Q-03) | https://docs.sms-gate.app/pricing/ |
| Basemap | Protomaps build → self-hosted PMTiles | No | ODbL: "© OpenStreetMap contributors". Do not use the hosted Tile API (non-commercial only) | https://docs.protomaps.com/basemaps/downloads |
| Routing data | Geofabrik Algeria extract (287 MB) | No | ODbL attribution | https://download.geofabrik.de/africa/algeria.html |
| Facility seed | Overpass API, one-off export | No | Not used at runtime (usage policy) | https://wiki.openstreetmap.org/wiki/Overpass_API |
| Monitoring (optional) | UptimeRobot Free; Grafana Cloud Free | No | 50 monitors / 14-day retention | https://uptimerobot.com/pricing/ · https://grafana.com/pricing/ |
| ~~AI fallback (optional)~~ | ~~Gemini API~~ | — | Removed: Brev only (TD-27) | — |
| Email (optional) | Mailpit (self-hosted); Brevo Free | No | 300 emails/day after account approval | https://www.brevo.com/pricing/ |

**Excluded:**

- Twilio.
- Hosted map tile APIs.
- build.nvidia.com as the critical path.
- Paid GPU clouds other than Brev.
- Sentry, Resend and Better Stack: their official pages do not confirm that no card is required.

---

## 3. Licence map (PRD NFR-LIC-001)

| Component | Licence | Path |
|---|---|---|
| RF-DETR | Apache-2.0 | Core |
| supervision | MIT | Core |
| Qwen3-VL-8B | Apache-2.0 | Core |
| vLLM | Apache-2.0 | Core |
| MediaMTX | MIT | Core |
| FastAPI, PostGIS, Redis, OSRM, MapLibre | Permissive (MIT / BSD / PostgreSQL / GPL-compatible server use) | Core |
| Smoke/fire detector (`fire_smoke_box` YOLO26n or D-Fire YOLOv5) | AGPL-3.0 derived | Optional, isolated, off by default in production |
| Demo datasets (TAD, CADP, UCF-Crime, AI City) | Research / non-commercial | Demo footage only |

---

## 4. Technical open questions

| ID | Question | Owner | Due |
|---|---|---|---|
| TQ-01 | GPU tier: L40S (recommended) or L4 (fallback)? Check live Brev prices; $90 budget. | Tech lead | Day 1 |
| TQ-02 | Measured latency of RF-DETR + Qwen3-VL-8B-FP8 on the chosen GPU. Validates PRD NFR-PERF-001 and NFR-PERF-003. | Vision owner | Day 1 |
| TQ-03 | Exact capcom6 request format (`textMessage` vs `message`), webhook signing, and private-server deployment details. | Backend owner | Before P2 |
| TQ-04 | Pin exact image tags: MediaMTX, vLLM, PostGIS, OSRM. | Tech lead | P0 |
| TQ-05 | Does Dokploy support wildcard TLS? If not, one certificate per subdomain. | Tech lead | P0 |
| TQ-06 | Do boxes / track IDs drawn on the verifier frames help or hurt? (The ACCIDENT 1st place found drawn tracking trails hurt.) Run as an ablation; default = timestamps only. | Vision owner | P1 |
| TQ-07 | Yes-probability thresholds for `confirmed` / `probable` / `possible` and for the sweep, tuned on non-held-out normal, jam and crash clips to keep SC-005. | Vision owner | P1 |

---

## 5. Requirement-to-component map

| PRD area | Component (repo path) |
|---|---|
| CAM | `services/camsim` + MediaMTX |
| VIS | `services/vision` (+ vLLM on the GPU host) |
| INC, DSP, NTF, KPI, SEC, ADM | `services/api` (+ arq worker, PostGIS, Redis, OSRM) |
| RSP, HSP, CIT, MAP | `apps/web` (surfaces `/ops`, `/respond`, `/hospital`, `/try`) |
| Contracts | `packages/shared` + FastAPI routes → `contracts/` (generated) → `packages/api-client` |
| Evaluation | `eval/` |

---

## 6. Detection parameters (defaults; tune on non-held-out footage only)

Serves PRD FR-VIS-004, FR-VIS-005, FR-VIS-009 and FR-VIS-010. Every value is configurable per camera.

| Parameter | Default | Requirement |
|---|---|---|
| Frame analysis rate | 5 frames/s | FR-VIS-001 |
| Relative speed | Pixel displacement per second ÷ box height, median over 0.5–1 s ("lengths/s") | FR-VIS-003 |
| `collision_candidate` | Box overlap IoU > 0.05 (or centre distance < 0.6 × mean box width), **then** both tracks below 0.1 lengths/s for ≥ 3 s | FR-VIS-004 |
| `hard_stop` | Relative speed drops by > 70% within ≤ 1 s, then stays near zero ≥ 2 s, while < 30% of the other tracks slow down | FR-VIS-004 |
| `stalled_vehicle` | Stationary ≥ 20 s inside a live-lane polygon while other tracks still move | FR-VIS-004 |
| `pedestrian_on_road` | Person inside the carriageway polygon ≥ 2 s (highway cameras) | FR-VIS-004 |
| Confirmation frames before a stop counts | N = 3 consecutive frames | PRD E-04 |
| Evidence clip | ≥ 10 s before + ≥ 5 s after the trigger | FR-VIS-005 |
| Verifier input | One video: 16 frames at 4 fps over ±2 s + 4 context frames from −8 s to +4 s; 768 px long side; timestamp drawn on each frame | FR-VIS-005 |
| AI sweep | Every 5 s per camera; last 8 s at 2 fps; 640 px; one video | FR-VIS-015 |
| Upload pass 1 / pass 2 | Whole clip at 1–2 fps (max 64 frames) / ±2–3 s at 4 fps; correction damped (×0.35) and capped at ±1.5 s | FR-CIT-002 |
| Status thresholds | Yes-token probability: `confirmed` ≥ 0.8 with a rule trigger; `probable` 0.5–0.8 (or sweep ≥ threshold on 2 consecutive sweeps); below → `possible`. Starting values, tune per TQ-07 | FR-VIS-007 |
| Verifier answer format | JSON: `collision_visible` (yes / no / cannot_judge), `t_contact`, `type` (collision / rollover / fire / stalled / pedestrian / none), `vehicles_involved`, `lanes_blocked`, `findings[]` (statement, observed or inferred, `frame_ids`), `not_assessable[]`, `priority_raise` (0 or 1, with a finding), `description_fr`, `description_ar`. Guided decoding, temperature 0, no thinking | FR-VIS-005, FR-VIS-016 |
| Verifier timeout | 15 s | FR-VIS-009 |
| Repeat-trigger cooldown, same location | 120 s | FR-VIS-010 |
| "Try it" live session forced verifier check | every 4 s | FR-CIT-003 |

## 7. Data model (fields)

Serves PRD §12.

```
cameras(id, name, stream_url, geom Point, road, pk_km, heading_deg, wilaya, zones jsonb, calibration jsonb, status)
incidents(id, short_code, type, status, priority, priority_reasons jsonb, geom Point, road, pk_km, wilaya,
          source[camera|citizen|operator], camera_id, event_time, detected_at, ai_signals jsonb,
          verifier_result jsonb, ai_status, quality_flags jsonb,
          people_reported, trapped_reported, merged_into, created_at)
incident_events(id, incident_id, kind, actor_id, payload jsonb, ts, prev_hash, hash)        -- append-only
evidence(id, incident_id, kind[clip|keyframe|photo], path, sha256, start_ts, end_ts)
facilities(id, kind[hospital|civil_protection|gendarmerie|police], name, geom, wilaya, capabilities jsonb,
           ready_state, contact_sms)
units(id, facility_id, agency, callsign, status, geom, phone)
dispatches(id, incident_id, unit_id, hospital_id, eta_s, route geojson, status, ts)
casualties(id, incident_id, triage_tag, avpu, resp_rate, pulse, spo2, bleeding, notes, reported_by, ts)
notifications(id, incident_id, channel, recipient, payload, status, attempts, provider_ref, ts)
users(id, name, role, agency, facility_id)
audit_log(id, actor, action, target, ts, ip, prev_hash, hash)                                 -- append-only
try_jobs(id, sandbox, status, input_path, outputs jsonb, expires_at)
```

The application database role has no UPDATE or DELETE on `incident_events` and `audit_log` (PRD NFR-SEC-002).

## 8. Engineering rules and traceability

Serves PRD NFR-MAINT-001, NFR-MAINT-002 and §21.

- **Contracts first.**
  - `contracts/openapi.yaml`, `contracts/events/*.schema.json`, `contracts/cap-profile.md` and `contracts/sms-grammar.md` are the source of truth.
  - They are generated from the Pydantic models and FastAPI routes (`make gen`), and the TS client from `contracts/openapi.json` (TD-29).
  - CI regenerates them and fails on any diff.
- **Replaceable parts.** The detector, the AI verifier, the SMS provider and evidence storage each sit behind an interface (`Detector`, `Verifier`, `SmsProvider`, `EvidenceStore`). Business logic never imports a vendor SDK directly.
- **Traceability:**
  - Python tests reference requirement IDs in their name or docstring, e.g. `test_FR_NTF_005_parses_triage`. There are no frontend tests (TD-28).
  - CI generates `docs/traceability.md` (ID → test files → status) from test names.
  - PR titles reference requirement IDs.
- **Integrity check in CI.** Grep `services/` for `random`, hardcoded incident payloads or demo flags (PRD FR-VIS-020).
- **SMS grammar** lives in `contracts/sms-grammar.md`. It implements the codes listed in PRD FR-NTF-005.

## 9. Reliability timings

Serves PRD NFR-REL-001, NFR-REL-002 and FR-NTF-004.

| Behaviour | Implementation |
|---|---|
| Stream reconnect | Exponential back-off from 1 s to 30 s, one process per camera |
| No lost candidates | Redis Streams with consumer groups. Acknowledgement after the DB commit; pending entries are re-claimed on restart |
| Notification retry | Undelivered after 30 s → retry up to 3 times with exponential back-off → operator alert on final failure |
| Camera fault | Stall > 10 s or disconnect → `camera_fault` (PRD FR-CAM-005) |
