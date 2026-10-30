# Onboarding, setup and troubleshooting

## 1. Install the tools (once)

| Tool | Version | Install |
|---|---|---|
| git | any recent | https://git-scm.com |
| Docker + Compose | Docker Desktop / Engine 24+ | https://docs.docker.com/get-docker/ |
| uv | 0.9+ (installs Python 3.12 itself) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node + pnpm | Node ≥ 22 (`.nvmrc` = 24), pnpm 10 | `corepack enable && corepack prepare pnpm@10 --activate` |
| GNU make | 3.81+ | preinstalled on macOS/Linux |
| GitHub CLI | 2.x, authenticated | `gh auth login` |
| NVIDIA Brev CLI | latest | https://docs.nvidia.com/brev/latest/ then `brev login` |
| Claude Code | latest | for `/implement-issue` and `/review-pr` |

`make doctor` checks all of this and tells you what is missing.

## 2. First run

```bash
git clone git@github.com:Nadjeet/nadjet.git && cd nadjet
make setup        # deps, git hooks (core.hooksPath=.githooks), .env from .env.example
make dev          # infra + API + web; Ctrl-C stops the apps, `make stop` stops containers
```

- API docs: http://localhost:8080/docs · readiness: http://localhost:8080/ready
- Web: http://localhost:5173 (shows the API/database/Redis status)
- MediaMTX (simulated cameras): RTSP `rtsp://localhost:8554/<camera-id>`, WebRTC
  `http://localhost:8889/<camera-id>`

### Dev users (one per role)

```bash
cp data/seed/users.example.yaml data/seed/users.yaml   # git-ignored; set your own passwords
make migrate
(cd services/api && uv run nadjet-api seed-users --file ../../data/seed/users.yaml)
```

Re-running is safe: existing usernames are skipped. Sign in at http://localhost:5173/login: each role lands on its surface (`operator`, `supervisor`, `auditor`, `admin` → `/ops`; the agency users → `/respond`; `hospital` → `/hospital`). Public pages are at `/public`. The component reference sheet is at `/ops/design`; palette, contrast values and the live-events design are in `apps/web/README.md`.
`NADJET_JWT_SECRET` is optional locally but required (≥ 32 chars) in production.

### Incident engine

`make dev` also runs `nadjet-api consume` (Procfile.dev): it persists candidates queued by
`POST /internal/candidates` (header `Authorization: Bearer $NADJET_INGEST_TOKEN`, plus an
`Idempotency-Key`). Without the consumer, candidates wait in the Redis Stream and are saved when
it restarts. Evidence files go under `NADJET_EVIDENCE_DIR`. Set `NADJET_SIGNING_KEY`
(`uv run nadjet-api gen-signing-key`) in production; a fixed insecure key is used locally.
Live updates: `GET /events` (Server-Sent Events, bearer token header).

### Notifications: SMS gateway and web push (FR-NTF, TD-13)

`make dev` also runs `nadjet-api worker` (arq): it sends notifications, re-checks delivery after
30 s, retries 3 times with back-off, then raises an operator alert on the incident timeline.

**SMS gateway (own SIM, no third-party provider).** Needs an Android phone with a SIM and the
[SMS Gateway for Android](https://docs.sms-gate.app/) app.

1. Set `NADJET_SMS_PRIVATE_TOKEN` and `NADJET_SMS_DB_PASSWORD` in `.env`, then `make infra-sms`
   (capcom6 server + MariaDB, port `NADJET_SMS_PORT`, default 3000).
2. The phone must reach the server over HTTPS (reverse proxy, or a tunnel for a laptop demo).
   In the app: Settings > Cloud Server: API URL `https://<host>/api/mobile/v1`, private token =
   `NADJET_SMS_PRIVATE_TOKEN`; enable "Cloud server", Start, choose **Sign Up**. The app then shows a
   generated username and password.
3. Put them in `.env`: `NADJET_SMS_GATEWAY_URL=https://<host>`, `NADJET_SMS_GATEWAY_USER`,
   `NADJET_SMS_GATEWAY_PASSWORD`. Set `NADJET_SMS_WEBHOOK_SECRET` and use the same value as the app's
   webhook signing key (Settings > Webhooks).
4. Register the webhooks (Basic auth with the app credentials), pointing at the API:
   `POST <gateway>/api/3rdparty/v1/webhooks` with `{"id":"in","url":"https://<api>/sms/inbound","event":"sms:received"}`
   and one each for `sms:sent`, `sms:delivered`, `sms:failed` with url `https://<api>/sms/status`.
   If your build does not sign webhooks, append `?token=<NADJET_SMS_WEBHOOK_SECRET>` to the URLs.
5. Check: `uv run nadjet-api send-test-sms --to +213XXXXXXXXX`.

Local mode (phone on the same LAN as the laptop) is only for the offline fallback. The message
grammar is in `contracts/sms-grammar.md`. A user is recognised by `users.phone`.

**Web push.** `uv run nadjet-api gen-vapid`, copy both lines to `.env`. Browsers subscribe with
`GET /push/public-key` + `POST /push/subscriptions`. Manual check: subscribe a browser, then
queue an alert for that user (`queue_alerts` + `enqueue_all` from `nadjet_api.notifications`).

**CAP 1.2.** `GET /incidents/<id>.cap.xml` (bearer token) returns the incident as a CAP alert
with Arabic and French `info` blocks.

### Demo videos (optional for most work)

Cameras are defined in `data/cameras.yaml` (zones in `data/zones/<camera-id>.json`, demo clips
listed in `eval/heldout.json`). Videos are **not** in git (research licences). Download the clips
by hand following `scripts/videos/fetch.md`, then normalise them:

```bash
bash scripts/videos/prepare.sh      # data/videos/raw/<camera-id>.* -> data/videos/<camera-id>.mp4
make camsim && make dev             # RTSP rtsp://localhost:8554/<id>, WebRTC http://localhost:8889/<id>
```

Cameras without a video file are skipped with a warning. `make dev` also syncs the camera
registry (`make seed-cameras`); operators read it with `GET /cameras`.

Simulator controls (FR-CAM-004), while `make dev` runs:

```bash
make camsim-list
make camsim-freeze CAM=cam-a1-pk42      # no new frames, RTSP session stays open
make camsim-unfreeze CAM=cam-a1-pk42
make camsim-outage CAM=cam-a1-pk42      # drops the stream path; make camsim-restore brings it back
make camsim-swap CAM=cam-a1-pk42 VIDEO=other.mp4
make camsim-restart CAM=cam-a1-pk42     # clip restarts from 0
```

## 3. AI inference: NVIDIA Brev only

All AI inference runs on the team's Brev GPU instance. There is no other provider, also not
for local development.

1. `brev login` (once). Ask the team lead to add you to the Brev organisation.
2. The instance (default name `nadjet-gpu`, set `NADJET_BREV_INSTANCE` in `.env`) runs
   `deploy/gpu/compose.yml`. Starting or creating instances spends credits: only the team
   lead does it.
3. Start the instance if stopped (team lead, spends credits): `brev start nadjet-gpu`.
4. `make brev-up` starts vLLM on it and waits until the model is loaded (~2 min after a start).
5. Connect: `make brev-forward` (localhost:18000 → instance:8000), then `make brev-check`.
   `make brev-unforward` closes the tunnel.
6. Live test: `make test-brev` (not part of `make test` or CI).

If Brev is unreachable, the app reports "AI unavailable" and keeps the rule-based signals.

## 4. Daily workflow

```bash
gh issue list                       # pick an issue
claude                              # in the repo root
/implement-issue 42                 # Sonnet 5.5: issue → PR to dev
/review-pr 57                       # Opus 5.5: review + fixes, then waits for your CI check
# check CI on GitHub, then tell Claude: "CI is green"
```

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `make setup` FAIL lines | Install the missing tool shown by `make doctor` |
| Port already in use (55432, 56379, 8080, 5173, 8554, 8889) | Stop the other service, or change `NADJET_PG_PORT` / `NADJET_REDIS_PORT` in `.env` (and the URLs) |
| `/ready` returns 503 | `make ps` — start infra with `make infra`; run `make migrate` |
| Integration tests fail with connection errors | They need `make infra`; they fail on purpose when infra is down |
| `check-contracts` fails | Run `make gen` and commit `contracts/` and `packages/api-client/src/schema.d.ts` |
| `commit-msg` hook rejects a commit | Use one line: `type(scope): summary` (≤ 72 chars, no body, no co-authors) |
| `pre-push` refuses to push | You are pushing to `dev`/`main` or force-pushing; push your feature branch instead |
| `brev not logged in` | `brev login` |
| `make brev-check` fails | Instance stopped or forward missing: `make brev-status`, then `make brev-forward` |
| `Server disconnected without sending a response` | The tunnel works but vLLM is not serving yet (model loading or container not started): `make brev-up`, then `make brev-check` |
| MediaMTX shows no cameras | Add videos to `data/videos/` and run `make camsim`, then restart `make dev` |
| PostGIS image fails on Apple Silicon | Use the repo's `imresamu/postgis` image (multi-arch); do not switch to `postgis/postgis` |

## 6. Clean up

- `make stop` — stop containers (keeps data) · `make down` — remove containers.
- `make clean` — remove caches and builds (keeps `.env`, dependencies, data).
- `make reset-db` — delete local PostGIS/Redis data (asks for confirmation).
