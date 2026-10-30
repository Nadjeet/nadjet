# Contributing

The binding rules are in [`AGENTS.md`](AGENTS.md). This page is the short human version.

## Flow

1. Every change starts from a GitHub issue (templates: feature, bug) with testable
   acceptance criteria and PRD requirement IDs.
2. Implement: `/implement-issue <n>` in Claude Code (Sonnet 5.5), or by hand following the
   same steps in `.agents/skills/implement-issue/SKILL.md`.
3. Review: `/review-pr <n>` (Opus 5.5). It fixes real gaps on the PR branch and then stops.
4. You check GitHub CI. When it is green, tell the agent "CI is green". It then merges the PR
   into `dev` (rebase), closes the linked issue and deletes the branch.
5. `dev` is promoted to `main` by a maintainer for releases and demo tags (`demo-v1`).

## Branches and commits

- Branch from the latest `dev`: `git fetch origin && git switch -c feat/42-short-slug origin/dev`.
- Never commit or push directly to `dev` or `main`; PRs always target `dev`.
- One-line Conventional Commits only: `feat(api): add inbound sms parser`. No body, no
  co-authors, no trailers. The `commit-msg` hook and CI enforce this.
- Never force-push or rewrite shared history.

## Quality bar

- `make ci` passes locally (lint, types, contracts, tests, build).
- Non-frontend code has unit and integration tests. **No frontend tests** of any kind.
- AI inference only through NVIDIA Brev; no other AI provider, ever.
- New configuration goes in `.env.example`; product changes in `PRD.md`; technical
  decisions in `docs/11-technical-decisions.md`.

## Maintainer note: protected branches

The git hooks block direct commits/pushes to `dev` and `main`. A maintainer bootstrapping the
repository can override them once with `NADJET_ALLOW_PROTECTED=1`; agents must never do so.
Enable GitHub branch protection on `dev` and `main` (require PRs and the CI checks) to enforce
the same rule on the server.
