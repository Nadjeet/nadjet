# 09 — GitHub Organization: Repositories and Per-Repo Stack

The product is **Nadjet (نجاة)**. GitHub organization: **`Nadjeet`** (https://github.com/Nadjeet). Product monorepo: **`Nadjeet/nadjet`**. GHCR image names are lowercase: `ghcr.io/nadjeet/nadjet-*`.

## 1. Recommendation: one product monorepo, plus one tiny org repo

| Repo | Visibility | Purpose |
|---|---|---|
| **`Nadjeet/nadjet`** | Public for the hackathon (it signals transparency and satisfies AGPL if any AGPL component is used). Make it private later for the product. | The entire product: contracts, camera simulator, vision and AI, API, web apps, deploy configs, docs. |
| **`Nadjeet/.github`** | Public | Org profile README (`profile/README.md`), shared issue/PR templates, CODEOWNERS defaults, SECURITY.md. It costs nothing and makes the org look credible to a ministry evaluator. |

That is all. **Do not create** separate `api`, `web`, `vision`, `infra` or `models` repos now.

### Why a monorepo is the right call here (and not polyrepo)

1. **Contracts change atomically.**
   - The incident schema, the event JSON Schemas, the SMS grammar and the CAP profile are shared by the vision workers (Python), the API (Python) and three web apps (TypeScript).
   - In a monorepo, one PR changes the schema, regenerates the clients and fixes every consumer, and CI proves they agree.
   - In a polyrepo, the same change means 3–4 coordinated PRs and a version-skew bug on stage.
2. **The agent workflow fits a monorepo.**
   - Claude Code and Codex see the whole system: one `AGENTS.md`, one `CLAUDE.md`, one set of skills.
   - Parallel agents still stay isolated: one git worktree per workstream, with folder ownership rules (doc 07).
   - Cross-repo agent work is much harder: no shared context, separate checkouts, no cross-repo atomic PRs.
3. **The deployment tooling supports it.**
   - Dokploy has **Watch Paths** (glob filters such as `apps/web/**`) so that only the changed component redeploys ([docs](https://docs.dokploy.com/docs/core/watch-paths)).
   - Dokploy also takes a per-app Dockerfile path and build context ([docs](https://docs.dokploy.com/docs/core/applications/build-type)).
   - GitHub Actions supports `paths:` filters for per-component image builds.
4. **A small team has one CI, one issue tracker, one release tag** ("demo-v1"), and one place the jury can browse.
5. **Splitting later is cheap. Merging later is expensive.** When a government contract needs it (say, an on-prem vision SDK delivered separately), extract `services/vision` with `git filter-repo`, keeping its history.

**Where not to use the monorepo:**
- **Model weights and videos are never committed.**
  - Weights come from their original Hugging Face / GitHub sources at build or boot time. Licences matter: several are non-commercial or gated.
  - Demo videos come from a fetch script plus a private object-storage bucket.
- **The Android SMS gateway is a third-party APK** (capcom6, Apache-2.0). It is installed on the phone, not forked.

## 2. `nadjet` layout

```
nadjet/
├─ AGENTS.md  CLAUDE.md  README.md  LICENSE  justfile  .editorconfig
├─ contracts/                    # single source of truth
│  ├─ openapi.yaml               # REST API (generated from FastAPI, committed + diff-checked in CI)
│  ├─ events/*.schema.json       # incident.candidate, overlay, job.result …
│  ├─ cap-profile.md             # CAP 1.2 mapping
│  └─ sms-grammar.md             # outbound/inbound SMS codes
├─ packages/
│  ├─ shared/                    # Pydantic event models (source of truth) → contracts/events/*.schema.json
│  └─ api-client/                # TS types + fetch client generated from contracts/openapi.json
├─ services/
│  ├─ api/                       # FastAPI core: incidents, dispatch, triage, CAP, SMS webhook, jobs, SSE
│  ├─ vision/                    # GPU workers: ingest, detect, track, triggers, VLM verify, evidence, try-it jobs
│  └─ camsim/                    # camera simulator: mediamtx.yml generator, camctl, video prep
├─ apps/
│  └─ web/                       # one Vite SPA, 4 surfaces: /ops, /respond (PWA), /hospital, /try (public)
├─ deploy/
│  ├─ vps/compose.yml            # Dokploy "Docker Compose" project (core + media)
│  ├─ gpu/compose.yml            # Brev GPU host (vLLM + vision workers)
│  ├─ local/compose.yml          # local infra: PostGIS, Redis, MediaMTX
│  └─ mediamtx/mediamtx.yml
├─ data/                         # seeds: facilities.csv, units.csv, cameras.yaml, zones/, fetch scripts (no media)
├─ eval/                         # held-out clip list, run_eval.py, results/*.json
├─ docs/                         # these documents
└─ .github/workflows/            # ci.yml, images.yml (path-filtered), deploy.yml
```

**Workspace tooling:**
- **uv workspace** for Python (`services/api`, `services/vision`, `services/camsim`, `packages/shared`).
- **pnpm workspace** for TypeScript (`apps/web`, `packages/api-client`).
- **GNU `make`** as the single task runner (`make help`; TD-26).

**No Turborepo or Nx.** There is only one TS app, so a build orchestrator adds config without saving time.

## 3. Exact stack per component (and why)

### `services/api`: coordination backend

| Choice | Why |
|---|---|
| Python 3.12, **FastAPI**, Pydantic v2, Uvicorn | Same language and models as the vision workers. Native WebSocket and SSE. Auto-generates the OpenAPI spec that drives the TS client. |
| **SQLAlchemy 2 + Alembic**, GeoAlchemy2 | Mature migrations and PostGIS types. |
| **PostgreSQL 16/17 + PostGIS** (`postgis/postgis` image) | KNN "nearest unit/hospital" queries, geofences per wilaya, and JSONB for AI signals. |
| **Redis** (Streams + Pub/Sub) | Incident-candidate stream with consumer groups, notification jobs, the try-it job queue, and overlay fan-out. |
| **arq** (async Redis jobs) | Notification retries and SMS sending. Lighter than Celery and async-native like FastAPI. |
| httpx, python-telegram-bot, pywebpush | SMS gateway client, Telegram, Web Push. |
| lxml | CAP 1.2 XML generation and validation against the OASIS XSD. |
| PyNaCl | Ed25519 signing of the evidence hash chain. |
| OSRM HTTP client | `/table` and `/route` calls for ETA ranking. |
| pytest, ruff, mypy | Tests, lint, types. |

The API and the arq worker are **one image with two commands**, which means less to build and deploy.

### `services/vision`: GPU inference workers

| Choice | Why |
|---|---|
| Python 3.12, **PyAV** | RTSP/WHIP ingest with packet-level access, so evidence clips are cut without re-encoding. Clean reconnects. |
| **RF-DETR** (`rfdetr`, Apache-2.0) | COCO vehicles and persons. Permissive licence, so it is usable in a government product. Real-time on GPU (2.3–4.4 ms on a T4 with TRT per the authors). |
| **supervision** (MIT) | ByteTrack, `PolygonZone`, speed relative to box size, annotators for drawing the overlay video. |
| **vLLM** serving **Qwen3-VL-8B-Instruct (FP8)** (Apache-2.0) | The no-training crash *verifier, describer and AI sweep*. Structured JSON output, yes-token probabilities. This model family won the CVPR 2026 ACCIDENT challenge (doc 04). |
| Optional: smoke/fire detector (`fire_smoke_box` YOLO26n or D-Fire YOLOv5s; AGPL-derived) | Smoke and fire signal. **Separate process behind a feature flag**, off by default in production, so the core path stays permissively licensed. |
| ffmpeg with **h264_nvenc** | Republishes the annotated stream back to MediaMTX on the GPU encoder. |
| CUDA base image `nvidia/cuda:12.x-runtime` + PyTorch | GPU runtime. |

The vision image runs **in two modes**:
- `vision camera --id cam-a1-pk42`: one process per camera.
- `vision jobs`: processes "try it yourself" uploads and live phone sessions.

### `services/camsim`: camera simulator

| Choice | Why |
|---|---|
| **MediaMTX** (RTSP/WHIP in; WebRTC-WHEP, LL-HLS, RTSP out) | One binary covers simulated cameras, annotated republish, **phone-as-camera via WHIP**, and browser playback. |
| ffmpeg (`-re -stream_loop -1 -c copy`) via MediaMTX `runOnInit` | Each video file becomes a real RTSP camera. |
| `camctl` (Python + Typer) | Freeze, outage, restart and swap through the MediaMTX API and process signals. |

### `apps/web`: one SPA, four surfaces

| Choice | Why |
|---|---|
| **Vite + React 19 + TypeScript** | A static build, so it ships as a tiny nginx image. No SSR or server runtime is needed. It is the team's strongest stack, which means the fastest delivery. |
| **TanStack Router + TanStack Query** | Typed routes per surface (`/ops`, `/respond`, `/hospital`, `/try`) and cache plus SSE invalidation. |
| **Tailwind + shadcn/ui** | Fast, consistent, accessible UI. |
| **MapLibre GL + PMTiles** (Protomaps Algeria extract) | Offline, sovereign basemap with Arabic and French labels. |
| **vite-plugin-pwa** (Workbox) + IndexedDB queue | Installable responder app that works offline, with an SMS fallback path. |
| **i18next** (ar/fr/en, RTL) | Algerian bilingual users. |
| WHEP player (MediaMTX `reader.js` or a small `RTCPeerConnection` client); WHIP publisher for `/try/live` | Live camera wall, and the phone camera as a stream source. |
| No frontend tests | Testing policy (TD-28): the web app is validated with lint, type-check and build only. |

**Why one app, not four:** shared auth, design system, map components and API client. Each route bundle is code-split, so the responder PWA stays small. Separate subdomains point to the same container through Traefik host rules.

## 4. CI/CD (GitHub Actions)

```
ci.yml       on PR:   ruff+mypy+pytest unit+integration (PostGIS/Redis services) · eslint+tsc+build (web, no tests) · contracts drift · integrity + commit rules
                      (regenerate openapi/clients → git diff --exit-code) · CAP XSD validation · integrity grep
                      (no `random`/hardcoded incidents in services/)
images.yml   on push to main, path-filtered:
                      services/api/**   → ghcr.io/nadjeet/nadjet-api:{sha,main}
                      services/vision/** → ghcr.io/nadjeet/nadjet-vision:{sha,main}   (CUDA, built on GH runner, never on the VPS)
                      apps/web/**       → ghcr.io/nadjeet/nadjet-web:{sha,main}
deploy.yml   after images.yml: POST Dokploy deploy webhook for the VPS compose project (or Dokploy GitHub App auto-deploy)
```

**Build images in CI and push them to GHCR.** Dokploy only pulls. Building CUDA images (5–15 GB) on a small VPS is slow and fills the disk, and Dokploy re-clones the repo on every auto-deploy ([docs](https://docs.dokploy.com/docs/core/docker-compose)).

## 5. Branch and agent conventions

- `main` is protected. PRs need green CI plus one human review.
- Workstream branches look like `ws2/vision-triggers`, one git worktree per agent.
- Tags: `demo-v1` marks the frozen stage build. **Stage deploys pin to the tag, never to `main`.**
- Conventional commits scoped by folder: `feat(vision): …`, `fix(api): …`.
