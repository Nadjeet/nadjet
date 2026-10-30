---
paths:
  - "services/**/*.py"
  - "packages/shared/**/*.py"
---

# Python services and shared package

- Every behaviour change ships with pytest tests in the package's `tests/` folder:
  unit tests (no network: fakes, `httpx.MockTransport`, FastAPI `TestClient` with injected
  dependencies) and, when it touches PostGIS/Redis, `@pytest.mark.integration` tests that hit
  the real local infra and fail (never skip) when it is down.
- Keep pure logic (rules, scoring, parsing) in plain functions so it is unit-testable.
- Configuration only through `NADJET_*` settings classes; add new variables to `.env.example`.
- After changing FastAPI routes or `nadjet_shared` models run `make gen` and commit
  `contracts/` and `packages/api-client/src/schema.d.ts`.
- Database schema changes need an Alembic migration (`cd services/api && uv run alembic
  revision -m "..."`), with a working `downgrade`.
- AI calls go only through `nadjet_vision.inference.BrevVlmClient` (Brev-only rule).
- Run `make lint typecheck test` before committing.
