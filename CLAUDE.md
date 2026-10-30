@AGENTS.md

## Claude Code specifics

- Project skills: `/implement-issue <n>`, `/review-pr <n>` (plus the third-party skills listed
  above). They live in `.agents/skills/` and are symlinked into `.claude/skills/`.
- Subagents: `researcher` (external docs and discussions, read-only) and `verifier`
  (independent re-check of a change against its issue). Use `Explore` for codebase search.
- Area rules in `.agents/rules/` are linked into `.claude/rules/` and load automatically for
  matching paths.
- `.claude/settings.json` disables commit/PR attribution and adds guard hooks; personal
  overrides go in `.claude/settings.local.json` (git-ignored).
