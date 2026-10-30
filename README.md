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
| `make brev-forward` · `make brev-check` | Connect to and verify the AI server on NVIDIA Brev |
| `make clean` · `make reset-db` | Remove caches/builds · delete local data (asks first) |

## AI development workflow

Work is driven by GitHub issues and two Claude Code skills:

- `/implement-issue <n>` — researches, plans, implements with tests, and opens a PR to `dev`.
- `/review-pr <n>` — reviews independently, fixes gaps, then waits for you to confirm CI is
  green before merging into `dev`, closing the issue and deleting the branch.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branches, commits and the review gate.
