# AGENTS.md — Nadjet (نجاة)

Single source of truth for every coding agent (Claude Code, Codex, others) and for humans.
`CLAUDE.md` imports this file; `.claude/` and `.agents/` only add tool wiring, never new rules.

## Product in one paragraph

Nadjet detects road crashes on existing CCTV with AI, collects citizen reports elsewhere, and
coordinates the emergency response (units, hospital, SMS/app alerts) for Algeria. **What** to
build: `PRD.md` (requirement IDs like `FR-VIS-007`). **How**: `docs/11-technical-decisions.md`
(`TD-xx`, wins over docs 04–10). Always cite requirement IDs in plans, tests and PRs.

## Repository map

| Path | What | Stack |
|---|---|---|
| `services/api` | Coordination API (`nadjet_api`) | Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Redis |
| `services/vision` | Vision workers + AI client (`nadjet_vision`) | Python; heavy GPU deps only in the `gpu` extra |
| `services/camsim` | Simulated cameras → MediaMTX config (`nadjet_camsim`) | Python |
| `packages/shared` | Event contracts (`nadjet_shared`, Pydantic) | Python |
| `packages/api-client` | Typed TS client generated from `contracts/openapi.json` | TypeScript |
| `apps/web` | Web app (operator, responder, hospital, public) | React 19, Vite, Tailwind |
| `contracts/` | **Generated** OpenAPI + event JSON Schemas (never hand-edit) | — |
| `deploy/local` · `deploy/gpu` | Local infra (PostGIS, Redis, MediaMTX) · vLLM on Brev | Docker Compose |
| `data/` · `eval/` | Camera catalogue, demo data (no media in git) · evaluation | — |
| `.agents/rules/` | Area rules — read the one for the area you touch | — |

## Commands (always use make)

`make setup` · `make dev` · `make stop` · `make test` · `make test-unit` · `make lint` ·
`make typecheck` · `make format` · `make gen` · `make check-contracts` · `make build` ·
`make ci` · `make doctor` · `make brev-forward` · `make brev-check` · `make help` for all.

Definition of done for any change: `make format && make lint && make typecheck &&
make check-contracts && make test` all pass locally (plus `make build` when build files change).
Report exact commands and results. Never claim a check passed if you did not run it.

## Testing policy (strict)

- **Frontend: never create tests.** No unit, component, integration, UI or end-to-end tests
  for `apps/web` or `packages/api-client` (no Vitest, Jest, Playwright, Cypress, `*.test.*`,
  `*.spec.*`). `scripts/check-integrity.sh` fails CI if any appear. Validate frontend changes
  with `make typecheck`, `make lint` and `pnpm build`.
- **Everything else: unit + integration tests are required** (pytest). Cover business logic,
  API contracts, error handling, edge cases and integrations.
  - Unit tests: no network, no infra; use fakes / `httpx.MockTransport`.
  - Integration tests: `@pytest.mark.integration`, real PostGIS/Redis from `make infra`.
    They must **fail, not skip**, when infra is down.
  - `@pytest.mark.brev`: live Brev endpoint; never in CI; run with `make test-brev`.
- Name tests after behaviour and reference requirement IDs in docstrings where relevant.

## AI inference — NVIDIA Brev only

- All AI inference (local dev, tests against live models, demo, production pilot) runs on the
  team's NVIDIA Brev instance (`deploy/gpu/compose.yml`, vLLM, `Qwen/Qwen3-VL-8B-Instruct-FP8`).
- Locally: `make brev-forward` (localhost:18000 → instance:8000), then `make brev-check`.
- **Never add, call or fall back to another AI provider** (OpenAI, Gemini, Anthropic API, NVIDIA
  build.nvidia.com, Ollama, local MLX…). If Brev is unavailable, surface "AI unavailable"
  (PRD FR-VIS-009); do not degrade silently. `scripts/check-integrity.sh` enforces this.
- Never create, start, stop or delete Brev instances, or spend credits, without the user's
  explicit approval in chat. Never print Brev tokens or other credentials.

## Integrity rules (PRD FR-VIS-020..022)

- Never create incidents, detections or confidence values from hardcoded data, timestamps,
  file names or random values. Mocked AI answers are allowed **only in tests**.
- Every AI value shown to users carries its source (rule name or model id).
- Demo clips come from the held-out list (`eval/heldout.json`); never tune on them. Only the
  catalogue validators and `eval/run_eval.py` may reference that file;
  `scripts/check-integrity.sh` fails otherwise.

## Code conventions

- Python: typed (`mypy --strict` clean), Ruff-formatted, Pydantic v2 models at boundaries,
  settings via `NADJET_*` env vars (`pydantic-settings`), async I/O in services.
- TypeScript: strict, ESLint + Prettier, API calls only through `@nadjet/api-client`.
- Contracts: change Pydantic models / FastAPI routes, then `make gen`; commit generated files.
- DB changes: Alembic migration in `services/api/src/nadjet_api/migrations/versions/`.
- Keep dependencies minimal; prefer maintained, permissively licensed libraries
  (copyleft/non-commercial only behind a flag, off by default — PRD D-06).
- No secrets in git. `.env` is local; document new variables in `.env.example`.

## Git rules

- Always branch from the latest `dev`: `git fetch origin && git switch -c <branch> origin/dev`.
- Branch names: `<type>/<issue>-<short-slug>`, e.g. `feat/42-sms-inbound-parser`.
- **Never commit or push directly to `dev` or `main`.** All work goes through PRs targeting `dev`.
- Commits: **one-line Conventional Commits** — `type(scope): summary` (≤ 72 chars, imperative,
  lowercase). Types: feat, fix, refactor, perf, test, docs, build, ci, chore. Scopes: api,
  vision, camsim, shared, web, client, infra, agents, docs. One logical change per commit.
- **Never add co-authors** or any trailer (`Co-Authored-By`, "Generated with …").
- Never force-push, rewrite published history, `git reset --hard`, `git clean -fd`, delete
  branches or close issues/PRs unless the workflow below explicitly allows it, or the user
  explicitly authorizes it in chat.
- Preserve unrelated working-tree changes: never stash, discard or commit files you did not
  change. If the tree has unrelated changes, work in a separate git worktree.
- Git hooks in `.githooks/` (installed by `make setup`) enforce message format, no trailers,
  and no direct pushes to `dev`/`main`.

## AI development workflow

The daily loop is two Claude Code skills (source in `.agents/skills/`):

1. `/implement-issue <n>` (Sonnet 5.5): issue → research → plan → branch from `dev` →
   implement + tests + docs → full validation → one-line commits → push → PR to `dev`
   that links the issue (`Closes #n`).
2. `/review-pr <n>` (Opus 5.5): independent review against the issue and PRD → fix real gaps
   with commits on the PR branch → re-validate until the issue is truly satisfied → **stop and
   wait** for the user to confirm GitHub CI is green.

**CI approval gate:** never merge or close a PR before the user explicitly confirms CI is green
in chat. After that confirmation (and re-checking `gh pr checks`): merge the PR into `dev`
(rebase), close its linked issue(s), delete the PR branch locally and remotely. Only touch the
PR, the issue(s) it links and its own head branch — verify the relationship first.

Codex and other agents follow the same steps by reading `.agents/skills/implement-issue/SKILL.md`
and `.agents/skills/review-pr/SKILL.md`.

## Installed third-party skills

Managed by `npx skills` (`skills-lock.json`): brev-cli, fastapi, shadcn,
vercel-react-best-practices, supabase-postgres-best-practices, docker-compose-patterns,
systematic-debugging, verification-before-completion. Update with
`npx skills update -y` and review diffs before committing. Never install skills unattended.
