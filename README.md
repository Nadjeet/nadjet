# Nadjet (نجاة)

AI road-incident detection and emergency coordination for Algeria. Nadjet spots crashes on
existing road cameras, collects citizen reports where there are no cameras, and coordinates
the rescue: right unit, right hospital, alerts by app and SMS, even without mobile data.

- Product requirements: [`PRD.md`](PRD.md)
- Technical decisions: [`docs/11-technical-decisions.md`](docs/11-technical-decisions.md)
- Research and design: [`docs/`](docs/README.md)
- Rules for every contributor and coding agent: [`AGENTS.md`](AGENTS.md)

## Quick start

```bash
git clone git@github.com:Nadjeet/nadjet.git && cd nadjet
make setup      # checks tools, installs Python + Node deps, git hooks, creates .env
make dev        # PostGIS, Redis, MediaMTX, API (http://localhost:8080/docs), web (http://localhost:5173)
make test       # all non-frontend tests (unit + integration)
```

Requirements: git, Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node ≥ 22 with
pnpm 10, GNU make, `gh` (for the AI workflows) and the NVIDIA Brev CLI (for AI inference).
Full guide: [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

## Repository layout

```
apps/web              React 19 + Vite web app (operator, responder, hospital, public pages)
packages/api-client   TS client generated from contracts/openapi.json
packages/shared       Shared Pydantic event contracts (source of truth)
services/api          FastAPI coordination API (PostGIS, Redis, Alembic)
services/vision       Vision workers and the AI client (NVIDIA Brev only)
services/camsim       Simulated cameras: real videos → RTSP via MediaMTX
contracts/            Generated OpenAPI and JSON Schemas (do not edit)
deploy/local          Local infrastructure (Docker Compose)
deploy/gpu            vLLM server for the Brev GPU instance
data/  eval/          Camera catalogue · evaluation (no media in git)
scripts/              Doctor, Brev helpers, integrity checks
.agents/ .claude/     Agent skills, rules, hooks (see AGENTS.md)
```

## Everyday commands

| Command | What it does |
|---|---|
| `make help` | List every command |
| `make dev` / `make stop` | Start / stop the full local environment |
| `make test` · `make test-unit` | All tests with real infra · fast unit tests only |
| `make lint` · `make typecheck` · `make format` | Quality checks and auto-format |
| `make gen` · `make check-contracts` | Regenerate / verify contracts and the TS client |
| `make build` | Build Python wheels and the web app |
| `make ci` | Everything CI runs |
| `make doctor` | Diagnose the local environment |
| `make brev-up` · `make brev-forward` · `make brev-check` | Start, connect to and verify the AI server on NVIDIA Brev |
| `make brev-tunnel` · `make brev-deploy-workers` · `make brev-logs` | Run the vision workers on Brev against your local stack |
| `make clean` · `make reset-db` | Remove caches/builds · delete local data (asks first) |

## AI inference on NVIDIA Brev (GPU)

All AI inference runs on the team's shared NVIDIA Brev GPU instance `nadjet-gpu`. There is no
other AI provider. You only need this when working on AI features (`services/vision`):
the API, web app, cameras and all tests work without it.

### 1. Join the team's Brev organisation (once)

1. The team lead sends you a **private Brev invite link** (valid 7 days). Open it and create
   your free account. Never share the link: anyone who has it can join and use the team's
   credits.
2. Install the Brev CLI ([docs](https://docs.nvidia.com/brev/latest/)):

   ```bash
   brew install brevdev/homebrew-brev/brev                                  # macOS
   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"   # Linux
   ```

3. Log in and check you see the team instance:

   ```bash
   brev login
   brev ls            # must list nadjet-gpu
   ```

   If `brev login` offers to install the Brev agent skill, answer **no**: the repo already
   ships it (`.agents/skills/brev-cli`).

### 2. Run the GPU and connect

```bash
brev start nadjet-gpu   # only if `brev ls` shows it STOPPED — spends shared credits (~$1.74/h)
make brev-up            # starts the vLLM AI server on the instance, waits until the model is loaded (~2 min)
make brev-forward       # opens localhost:18000 -> nadjet-gpu:8000
make brev-check         # must print: OK ... serves Qwen/Qwen3-VL-8B-Instruct-FP8
make test-brev          # optional live test
```

### 3. Run the vision workers on Brev

The workers (`nadjet-vision camera`) run on the GPU instance, read the **local** simulated
cameras and report to the **local** API through ssh tunnels, so nothing is exposed publicly.

```bash
make dev                  # locally: infra, API, cameras (make camsim first, see docs/ONBOARDING.md)
make brev-tunnel          # vLLM -> localhost:18000, local RTSP -> instance:18554, local API -> instance:18080
make brev-deploy-workers  # pulls ghcr.io/nadjeet/nadjet-vision:dev (builds on the instance if absent) and starts workers
make brev-logs F=-f       # follow worker logs: camera=... fps=...
make brev-untunnel        # close all three tunnels when you are done
```

Details and the verification steps: [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

### 4. Stop it when you are done

```bash
make brev-untunnel      # close the tunnels (make brev-unforward if you only used brev-forward)
brev stop nadjet-gpu    # stop the GPU: billing stops, the model stays cached
```

Rules: credits are shared by the whole team. Never leave the instance running when nobody
uses it, and never `brev create` or `brev delete` instances. Tell the team in chat when you
start or stop `nadjet-gpu`. Troubleshooting: [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

## AI development workflow

Work is driven by GitHub issues and two Claude Code skills:

- `/implement-issue <n>` — researches, plans, implements with tests, and opens a PR to `dev`.
- `/review-pr <n>` — reviews independently, fixes gaps, then waits for you to confirm CI is
  green before merging into `dev`, closing the issue and deleting the branch.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branches, commits and the review gate.
