---
name: implement-issue
description: Implement a GitHub issue end to end — understand it, research, plan, branch from dev, implement with tests and docs, validate, commit with one-line Conventional Commits, push and open a PR to dev that closes the issue. Use only when the user runs /implement-issue <number>.
argument-hint: <issue-number>
disable-model-invocation: true
model: claude-sonnet-5-5
---

# /implement-issue $ARGUMENTS

Implement GitHub issue **#$ARGUMENTS** completely and open a PR targeting `dev`.
Follow `AGENTS.md` at all times (testing policy, Brev-only AI, integrity and git rules).
Work autonomously; ask the user only for a decision that is genuinely theirs (for example an
ambiguous requirement, a product trade-off, or spending Brev credits).

## 0. Preflight

```bash
gh auth status && git fetch origin --prune
git status --porcelain            # note any pre-existing changes: you must not touch them
gh issue view $ARGUMENTS --json number,state,title
```

- Stop if the issue is closed or does not exist, or if an open PR already references it
  (`gh pr list --state open --search "$ARGUMENTS in:body"`); report and ask.
- If the working tree has changes you did not make, do the whole task in a separate worktree:
  `git worktree add ../nadjet-wt-$ARGUMENTS origin/dev` and work there.

## 1. Understand the issue (no code yet)

```bash
gh issue view $ARGUMENTS --comments --json number,title,body,labels,milestone,comments,assignees
gh issue list --state all --search "<keywords>"          # related issues
gh pr list --state all --search "<keywords>"             # related past PRs
```

- Extract: goal, acceptance criteria, PRD requirement IDs (`FR-…`, `NFR-…`), constraints,
  out-of-scope items, and decisions made in comments. Read the referenced PRD sections and
  `docs/11-technical-decisions.md` rows.
- Write the acceptance criteria as a checklist. If a criterion is missing or ambiguous,
  derive it from the PRD; if it still conflicts, ask the user before implementing.

## 2. Research before implementing

- Delegate to the `researcher` subagent for the exact library versions in `uv.lock` /
  `pnpm-lock.yaml`: official docs, changelogs, known issues and recent (2026) discussions for
  the APIs you will use. Prefer primary sources. Keep the URLs for the PR description.
- **Load the installed skills that match what you touch** (invoke them; they hold the
  vetted conventions for this stack). Pick every row that applies:

  | You are changing | Use skill |
  |---|---|
  | FastAPI routes, dependencies, Pydantic models, SSE (`services/api`) | `fastapi` |
  | SQL, PostGIS queries, indexes, Alembic migrations | `supabase-postgres-best-practices` |
  | `deploy/**/compose.yml`, Dockerfiles, healthchecks | `docker-compose-patterns` |
  | React components, data fetching, performance (`apps/web`) | `vercel-react-best-practices` |
  | UI components (shadcn/ui, Tailwind) in `apps/web` | `shadcn` |
  | Brev instances, tunnels, GPU workers | `brev-cli` (never create/start/stop/delete instances without the user's approval) |
  | A failing test, bug or unexpected behaviour | `systematic-debugging` |
  | Before claiming the work is done | `verification-before-completion` |

## 3. Investigate the repository and follow its architecture

- Use the `Explore` subagent to map every file, contract, migration, test and doc the change
  touches. Read the matching `.agents/rules/*.md` and the related `docs/11` TD rows.
- **Respect the existing architecture and patterns — extend, don't reinvent:**
  - Code goes in the component that owns it (see the repository map in `AGENTS.md`); no new
    top-level packages or services unless the issue says so.
  - Python: one feature module per area inside the service package (e.g.
    `nadjet_api/<feature>/` with routes, models, service logic), pure logic in plain
    functions, settings via the existing `NADJET_*` `BaseSettings` classes, swappable
    dependencies behind small `Protocol` interfaces (like `Detector`, `Router`,
    `NotificationChannel`), async I/O, shared event contracts in `nadjet_shared`.
  - API: routes in FastAPI with response models; auth via the shared dependencies; every
    contract change followed by `make gen`.
  - Database: Alembic migration per change, based on the latest `origin/dev` revision
    (exactly one head, see `.agents/rules/python-services.md`).
  - AI: only through `nadjet_vision.inference.BrevVlmClient`; statuses via
    `nadjet_vision.status`; text through `nadjet_vision.safety`.
  - Web: TanStack Router/Query, `@nadjet/api-client` for every request, shared components
    (`PriorityBadge`, `AiSourceTag`, …), i18n strings in `locales/`, logical CSS for RTL.
  - Tests mirror the source layout in each package's `tests/`; integration tests use the
    `integration` marker.
- Match naming, error handling, logging and file layout of neighbouring code. Do not add
  libraries without need; if one is required, justify it in the PR and record a `TD-xx` row.
- If the issue conflicts with the existing architecture, stop and ask the user instead of
  working around it.

## 4. Plan

Produce a short plan before editing: files to change, data/contract changes, migrations,
tests per acceptance criterion (unit and integration; **no frontend tests**), docs to update,
and the commit sequence. Track it with your task list.

## 5. Branch from the latest dev

```bash
git fetch origin
git switch -c <type>/$ARGUMENTS-<short-slug> origin/dev
```

`<type>` is feat, fix, refactor, docs, test, build, ci or chore. Never work on `dev` or `main`.

## 6. Implement

- Implement every acceptance criterion. Keep changes focused on the issue.
- Tests: unit tests for logic and edge cases; integration tests (`@pytest.mark.integration`)
  for anything touching PostGIS/Redis or the HTTP API end to end. AI calls are mocked in tests
  with `httpx.MockTransport`; never call another AI provider.
- API or shared-model changes: run `make gen` and commit the generated files.
- Schema changes: Alembic migration with a working downgrade; before pushing, re-point its
  `down_revision` to the latest revision on `origin/dev` so there is exactly one head.
- Docs: update `AGENTS.md`, `docs/`, `.env.example` or the PRD (product changes only) when
  behaviour, commands or configuration change.

## 7. Validate (all must pass)

```bash
make format
make lint
make typecheck
make check-contracts
make test            # starts PostGIS/Redis, runs unit + integration tests
make build           # when build config, dependencies or the web app changed
```

- If the change touches AI inference and `make brev-check` succeeds, also run
  `make test-brev`; otherwise state in the PR that live Brev checks were not run.
- Fix failures at their root cause. Never skip, xfail or weaken a test to get green.

## 8. Commit at each logical step

```bash
git add <only the files of this step>
git commit -m "feat(api): add inbound sms parser"
```

- One-line Conventional Commit, no body, no trailers, **never a co-author**.
- Never commit unrelated files, secrets, media or generated config.

## 9. Push and open the PR

```bash
git push -u origin HEAD
gh pr create --base dev --head <branch> --title "<type>(<scope>): <summary>" --body-file <file>
```

PR body (use `.github/pull_request_template.md` sections):
- `Closes #$ARGUMENTS`
- Summary of the change and the requirement IDs covered.
- Acceptance criteria checklist, each with its evidence (test name or command).
- Validation: exact commands run and their results; what was not run and why.
- Research sources (URLs) and notable decisions or trade-offs.

## 10. Report

Reply with the PR URL, the acceptance-criteria status, validation results and any open
question. Do not merge; `/review-pr` handles review and the CI gate.
