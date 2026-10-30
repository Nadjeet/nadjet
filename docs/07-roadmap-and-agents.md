# 07 — Implementation Roadmap, Parallel Workstreams and Agent Workflow

## 1. Repository layout (ownership = folder)

```
nadjet/
  AGENTS.md            # shared rules for Codex + Claude Code (CLAUDE.md just includes/links it)
  CLAUDE.md
  justfile
  docker-compose.yml
  contracts/           # SINGLE SOURCE OF TRUTH — OpenAPI, event JSON Schemas, CAP profile, SMS grammar
  sim/                 # camsim: mediamtx.yml generator, camctl, video prep scripts
  vision/              # workers: ingest, detect, track, triggers, verifier, evidence, eval/
  ml/                  # dataset fetch, clip extraction, splits.json, verifier training notebooks
  api/                 # FastAPI app: incidents, dispatch, facilities, triage, notifier, cap, auth, audit
  web/                 # operator dashboard, responder PWA, hospital view, citizen page
  data/                # seeds (facilities.csv, units.csv, cameras.yaml), fetch scripts — no videos in git
  docs/
```

## 2. Workstreams

| WS | Owner (human + agents) | Folder | Delivers | Depends on |
|---|---|---|---|---|
| **WS0 Contracts & integration** | Tech lead | `contracts/`, root | Event schemas, OpenAPI skeleton, CAP profile, SMS grammar, compose, justfile, AGENTS.md. Merges PRs and runs the end-to-end test. | — (goes first, hour 0–3) |
| **WS1 Simulation & infra** | 1 agent | `sim/`, `docker-compose.yml` | MediaMTX config generator, camctl, video normalisation, OSRM graph, PMTiles | contracts (camera schema) |
| **WS2 Vision pipeline** | 1–2 agents | `vision/` | Ingest, detection, tracking, speed, zones, triggers, evidence ring buffer, overlay publisher, candidate publisher, health metrics | sim streams; candidate schema |
| **WS3 ML: verifier + evaluation** | 1 agent (+ GPU/Colab) | `ml/`, `vision/eval/` | Dataset fetch, clip mining, video-level splits, VideoMAE fine-tune, exported weights, `run_eval.py` with honest metrics | — (starts hour 0 in parallel) |
| **WS4 Core API** | 1–2 agents | `api/` | DB models and migrations, candidate consumer, dedupe/merge, priority, dispatch + OSRM, facilities, triage, CAP export, auth/RBAC, audit hash chain, SSE/WS | contracts |
| **WS5 Notifications & SMS** | 1 agent | `api/notifier/` | SMS gateway client, inbound SMS parser, Telegram, Web Push, retries, delivery status | contracts (SMS grammar) |
| **WS6 Operator dashboard** | 1–2 agents | `web/app/(ops)` | Camera wall (WHEP + canvas overlay), incident queue, incident detail with evidence, map, dispatch panel, KPI page, system page | OpenAPI + mock server |
| **WS7 Responder / hospital / citizen UIs** | 1 agent | `web/app/(field)` | Responder PWA (ack, status, triage form, offline queue), hospital pre-alert view, citizen report page; ar/fr/en + RTL | OpenAPI + mock server |
| **WS8 QA & demo** | 1 agent + a human | `tests/e2e`, `docs/` | Playwright end-to-end of the full scenario, demo script, rehearsal checklist, slides data | everything |

### Avoiding conflicts

1. **Contracts first.** WS0 freezes v0 of `contracts/` within the first ~3 hours.
   - The API generates its Pydantic models from it.
   - The web app generates its TS client from it (`openapi-typescript`).
   - Workers validate payloads against the JSON Schemas.
   - Contract changes happen only through a PR to `contracts/`, reviewed by WS0.
2. **Mocks unblock everyone.**
   - WS6 and WS7 develop against a Prism mock (`prism mock contracts/openapi.yaml`).
   - WS4 develops against `vision/tools/replay_candidates.py`, which replays **recorded real candidates** for development only. These are never used in the demo.
3. **One folder per workstream.** Agents may not edit outside their folder except through a contract PR. Use **git worktrees**, one per agent (`git worktree add ../nadjet-ws4 -b ws4/api`).
4. **Small PRs, a merge cadence of every ~3 hours**, and an end-to-end smoke test (`just e2e`) on main after every merge.
5. **Shared definitions of done** live in AGENTS.md: tests pass, lint passes, contract validated, no hardcoded demo events.

## 3. Timeline (48 h hackathon; adjust to the real schedule)

| Phase | Hours | Goal | Exit criterion |
|---|---|---|---|
| **P0 Foundation** | 0–4 | Contracts v0, repo skeleton, compose up, MediaMTX streaming 4 clips, dataset download started, detector benchmark on the laptop | `just infra && just sim` → 4 live streams in the browser |
| **P1 Vertical slice** | 4–14 | Camera → detector + tracker → `stalled_vehicle` / `collision_candidate` triggers → candidate → API → DB → SSE → dashboard card with clip | One real detected incident visible end-to-end |
| **P2 Response chain** | 14–26 | Verification, OSRM recommendation, dispatch, CAP, SMS out + inbound ACK, responder PWA, triage, hospital view | Full chain on real phones |
| **P3 Intelligence** | 14–30 (parallel) | Verifier trained and integrated, priority with reasons, VLM description, evaluation report | Ablation table produced on the held-out set |
| **P4 Polish** | 30–40 | Map, KPI timeline, ar/fr/en, camera health, merge with citizen report, evidence verify | Rehearsal 1 passes without manual DB edits |
| **P5 Freeze & rehearse** | 40–48 | Bug fixes only, demo script, slides, backup video recording of a real run | Two clean rehearsals |

**Fallbacks**, each still genuine:
- If the verifier is weak, alert on triggers and label the type `possible_collision`. The human verification step absorbs the uncertainty.
- If the VLM is slow, skip the description.
- If the SMS gateway fails, use Telegram plus the PWA.

## 4. Agent workflow recommendations

- **One human lead per 2–3 agents.** The human reviews diffs and keeps scope. Agents implement.
- **Claude Code** suits multi-file features and refactors that need repo context: API, dashboard, integration, plus subagents for review.
  - Give each workstream a short **skill** or slash command, e.g. `/new-endpoint` (adds an OpenAPI path, Pydantic model, router, test) and `/new-trigger` (adds a trigger, unit test on synthetic tracks, and a doc row).
- **Codex** suits well-specified, self-contained tasks: SMS parser, CAP serializer, hash-chain module, calibration tool, data-fetch scripts, test writing.
- **Research agents** handle one-off checks (exact API fields of the SMS gateway, an OSRM table response, MediaMTX API paths). They are read-only.
- **Reviewer agent** before each merge: correctness plus the "no fabricated results" rule.
  - grep for `random`, hardcoded timestamps, or `if demo` in `vision/` and `api/`.
- Don't run more than ~8 concurrent agents. Integration bandwidth is the bottleneck, not code generation.

### `AGENTS.md` starter (copy to repo root)

```markdown
# Nadjet (نجاة) — agent rules
## Scope
- Work only inside your workstream folder (see docs/07). Contract changes → PR to contracts/ only.
## Integrity (hard rules)
- Never create incidents, detections or confidences from hardcoded data, timestamps, filenames or random values.
- Never read files listed as held-out in ml/splits.json from training or tuning code.
- Every confidence shown to users must come from a model output or a documented rule; store its source.
## Stack
- Python 3.12 (uv), FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest, ruff.
- TypeScript, React, shadcn/ui, TanStack Query, MapLibre, vitest, Playwright, prettier/eslint.
## Contracts
- contracts/openapi.yaml, contracts/events/*.schema.json, contracts/cap-profile.md, contracts/sms-grammar.md.
- Regenerate clients after contract changes: `just gen`.
## Done = 
- tests + lint pass, `just e2e` green on your branch, no TODOs in user-facing paths, docs updated if behaviour changed.
## Commits
- Conventional commits scoped by folder: feat(vision): …, fix(api): …
```

`CLAUDE.md` contains: `See AGENTS.md. Additionally: use subagents for read-only research; never commit videos or model weights.`

## 5. Contracts to freeze first (WS0 checklist)

- `events/incident.candidate.schema.json`:
  - `camera_id`, `trigger_type`, `event_time`, `detected_at`
  - `bbox[]`, `track_ids[]`
  - `signals{speed_drop, stop_seconds, iou, ...}`
  - `verifier{model, version, p_crash}`
  - `evidence{clip_path, keyframes[], sha256}`
- `events/overlay.schema.json`: per-frame boxes, track ids, classes, speeds.
- `openapi.yaml`: `/cameras`, `/incidents` (list, get, verify, reject, merge), `/incidents/{id}/dispatch`, `/incidents/{id}/triage`, `/incidents/{id}.cap.xml`, `/incidents/{id}/verify-integrity`, `/facilities/nearest`, `/sms/inbound`, `/reports` (citizen), `/events` (SSE), `/kpis`, `/auth/*`.
- `sms-grammar.md`:
  - Outbound: `ACC|P{1-4}|lat,lon|road PK|nV|code`
  - Inbound: `OK code`, `ER code` (en route), `OS code` (on scene), `T code R# Y# G# B#`, `H code READY|DIVERT`, `ACCIDENT <free text>`
- `cap-profile.md`: field mapping incident → CAP 1.2 (`category=Transport/Rescue`, `urgency`, `severity`, `certainty`, `area/circle`, `info` in `ar` and `fr`).
