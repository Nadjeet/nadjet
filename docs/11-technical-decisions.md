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
| TD-01 | 2026-10-30 | **Crash verifier:** pretrained **Qwen3-VL-8B-Instruct-FP8** (Apache-2.0), served by **vLLM** with guided JSON output | Fine-tuned VideoMAE (needs training); Roboflow "accident" YOLO (leaky benchmarks); dashcam models (wrong viewpoint) | No training allowed (PRD C-02). Frozen Qwen3-VL is the base of the CVPR 2026 ACCIDENT challenge 1st place. Permissive licence | FR-VIS-005, FR-VIS-007, D-03 |
| TD-02 | 2026-10-30 | **Detector:** **RF-DETR** (Apache-2.0), COCO classes | Ultralytics YOLO11/26 (AGPL-3.0) | Permissive licence for a government product (PRD NFR-LIC-001); real-time on GPU | FR-VIS-002 |
| TD-03 | 2026-10-30 | **Tracking, zones, speed:** `supervision` (MIT): ByteTrack, PolygonZone, homography ViewTransformer | Ultralytics track mode (AGPL) | Detector-agnostic, permissive | FR-VIS-003, FR-VIS-004 |
| TD-04 | 2026-10-30 | **Optional modules, off by default:** Cosmos-Reason2-8B second opinion (NVIDIA Open Model License, gated); D-Fire YOLOv5s smoke/fire (weights MIT, code AGPL, isolated); UCF-Crime VideoMAE score (CC-BY-NC, demo only) | — | Extra signals without contaminating the core licence path | FR-VIS-012, FR-VIS-013, D-06 |
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
| TD-18 | 2026-10-30 | **GPU host:** **NVIDIA Brev**, 1× L40S (or L4 without Cosmos). Plain `docker compose` running vLLM and the vision workers. **Outbound connections only** (RTSP pull/push to the VPS, HTTPS to the API) | Brev tunnels (they require browser authentication); hosted inference APIs as the main path | Simple, documented, no inbound ports | NFR-PERF-001, NFR-PERF-003 |
| TD-19 | 2026-10-30 | **CI/CD:** GitHub Actions builds images and pushes them to **GHCR** (`ghcr.io/nadjeet/nadjet-{web,api,vision}`). Dokploy only pulls. Stage pins to the tag `demo-v1` | Building on the VPS | CUDA images are 5–15 GB; Dokploy re-clones on every deploy | NFR-MAINT-001 |
| TD-20 | 2026-10-30 | **Hosted AI fallback (optional):** Gemini API (Google AI Studio free tier), only for public sample clips and consented uploads | build.nvidia.com as the critical path (terms limit it to trial use; unofficial rate limit) | Free, no card, Algeria supported; restricted by PRD NFR-PRIV-002 | FR-CIT-005 |
| TD-21 | 2026-10-30 | **Offline fallback:** `deploy/local` runs the full stack on the laptop; Mac VLM = Qwen2.5-VL-7B 4-bit via mlx-vlm | — | Stage resilience | NFR-REL-003 |

---

## 2. External services in use (PRD constraint C-01: free, no credit card)

The team already owns: an NVIDIA Brev account, a VPS with Dokploy, and a domain name. Everything below was verified on 2026-10-30.

| Need | Service | Card? | Limits and caveats | Source |
|---|---|---|---|---|
| Code, CI, images | GitHub Free org, Actions, GHCR | No | Unlimited standard runners and free GHCR for **public** repos | https://docs.github.com/en/billing/concepts/product-billing/github-actions · https://docs.github.com/en/billing/concepts/product-billing/github-packages |
| Model weights | Hugging Face Hub (free token) | No | 5,000 file requests per 5 min with a token. Cosmos-Reason2 is gated; credit "Built on NVIDIA Cosmos" | https://huggingface.co/docs/hub/rate-limits |
| TLS | Let's Encrypt via Traefik | No | 50 certificates per domain per week; test against staging | https://letsencrypt.org/docs/rate-limits/ |
| Push | Web Push (VAPID) | No account | iOS requires the PWA on the home screen (16.4+) | https://webkit.org/blog/12945/meet-web-push/ |
| Chat alerts | Telegram Bot API | No | About 20 messages/min per group | https://core.telegram.org/bots/faq |
| SMS | SMS Gateway for Android (capcom6) | No account | **Our SIM pays the operator tariff** (PRD Q-03) | https://docs.sms-gate.app/pricing/ |
| Basemap | Protomaps build → self-hosted PMTiles | No | ODbL: "© OpenStreetMap contributors". Do not use the hosted Tile API (non-commercial only) | https://docs.protomaps.com/basemaps/downloads |
| Routing data | Geofabrik Algeria extract (287 MB) | No | ODbL attribution | https://download.geofabrik.de/africa/algeria.html |
| Facility seed | Overpass API, one-off export | No | Not used at runtime (usage policy) | https://wiki.openstreetmap.org/wiki/Overpass_API |
| Monitoring (optional) | UptimeRobot Free; Grafana Cloud Free | No | 50 monitors / 14-day retention | https://uptimerobot.com/pricing/ · https://grafana.com/pricing/ |
| AI fallback (optional) | Gemini API, AI Studio free tier | No | Algeria supported. Free-tier data may be used to improve Google products | https://ai.google.dev/gemini-api/docs/available-regions · https://ai.google.dev/gemini-api/terms |
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
| Cosmos-Reason2-8B | NVIDIA Open Model License (gated) | Optional |
| D-Fire YOLOv5 (code) | AGPL-3.0 | Optional, isolated |
| OPear VideoMAE UCF-Crime | CC-BY-NC-4.0 | Optional, demo only |
| Demo datasets (TAD, CADP, UCF-Crime, AI City) | Research / non-commercial | Demo footage only |

---

## 4. Technical open questions

| ID | Question | Owner | Due |
|---|---|---|---|
| TQ-01 | GPU tier: L40S (Qwen + Cosmos) or L4 (Qwen only)? Check Brev prices and credits in the console. | Tech lead | Day 1 |
| TQ-02 | Measured latency of RF-DETR + Qwen3-VL-8B-FP8 on the chosen GPU. Validates PRD NFR-PERF-001 and NFR-PERF-003. | Vision owner | Day 1 |
| TQ-03 | Exact capcom6 request format (`textMessage` vs `message`), webhook signing, and private-server deployment details. | Backend owner | Before P2 |
| TQ-04 | Pin exact image tags: MediaMTX, vLLM, PostGIS, OSRM. | Tech lead | P0 |
| TQ-05 | Does Dokploy support wildcard TLS? If not, one certificate per subdomain. | Tech lead | P0 |

---

## 5. Requirement-to-component map

| PRD area | Component (repo path) |
|---|---|
| CAM | `services/camsim` + MediaMTX |
| VIS | `services/vision` (+ vLLM on the GPU host) |
| INC, DSP, NTF, KPI, SEC, ADM | `services/api` (+ arq worker, PostGIS, Redis, OSRM) |
| RSP, HSP, CIT, MAP | `apps/web` (surfaces `/ops`, `/respond`, `/hospital`, `/try`) |
| Contracts | `contracts/` → `packages/py-contracts`, `packages/ts-client` |
| Evaluation | `eval/` |

---

## 6. Detection parameters (defaults; tune on non-held-out footage only)

Serves PRD FR-VIS-004, FR-VIS-005, FR-VIS-009 and FR-VIS-010. Every value is configurable per camera.

| Parameter | Default | Requirement |
|---|---|---|
| Frame analysis rate | 5 frames/s | FR-VIS-001 |
| `collision_candidate` | Box overlap IoU > 0.05 (or centre distance < 0.6 × mean box width), **then** both tracks < 1.5 m/s for ≥ 3 s | FR-VIS-004 |
| `hard_stop` | Speed drop > 6 m/s within ≤ 1.5 s, while < 30% of the other tracks slow down | FR-VIS-004 |
| `stalled_vehicle` | Stationary ≥ 20 s inside a live-lane polygon while other tracks still move | FR-VIS-004 |
| `pedestrian_on_road` | Person inside the carriageway polygon ≥ 2 s (highway cameras) | FR-VIS-004 |
| `rollover_candidate` | Box aspect ratio flips abruptly, then the track stops | FR-VIS-004 |
| Confirmation frames before a stop counts | N = 3 consecutive frames | PRD E-04 |
| Evidence clip | ≥ 10 s before + ≥ 5 s after the trigger | FR-VIS-005 |
| Keyframes sent to the verifier | 8–16 frames, about 448 px | FR-VIS-005 |
| Verifier answer format | JSON: `incident` (bool), `type` (collision / rollover / fire / stalled / pedestrian / none), `vehicles_involved`, `lanes_blocked`, `severity_hint`, `description_fr`, `description_ar`, `confidence`. Enforced by guided decoding, temperature 0 | FR-VIS-005 |
| Verifier timeout | 15 s | FR-VIS-009 |
| Repeat-trigger cooldown, same location | 120 s | FR-VIS-010 |
| "Try it" live session forced verifier check | every 4 s | FR-CIT-003 |

## 7. Data model (fields)

Serves PRD §12.

```
cameras(id, name, stream_url, geom Point, road, pk_km, heading_deg, wilaya, zones jsonb, calibration jsonb, status)
incidents(id, short_code, type, status, priority, priority_reasons jsonb, geom Point, road, pk_km, wilaya,
          source[camera|citizen|operator], camera_id, event_time, detected_at, ai_signals jsonb,
          verifier_result jsonb, merged_into, created_at)
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
  - The TypeScript and Python clients and models are generated from them (`just gen`).
  - CI regenerates them and fails on any diff.
- **Replaceable parts.** The detector, the AI verifier, the SMS provider and evidence storage each sit behind an interface (`Detector`, `Verifier`, `SmsProvider`, `EvidenceStore`). Business logic never imports a vendor SDK directly.
- **Traceability:**
  - Tests carry the requirement ID in their name, e.g. `test_FR_NTF_005_parses_triage` or `it("FR-CIT-006: …")`.
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
