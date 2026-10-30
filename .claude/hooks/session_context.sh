#!/usr/bin/env bash
# SessionStart: give the agent the current git context and the key rules (stdout becomes context).
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
echo "Nadjet repo — branch: ${branch}; uncommitted files: ${dirty}."
if [ "$branch" = "main" ] || [ "$branch" = "dev" ]; then
  echo "You are on ${branch}: never commit here. Branch from origin/dev before changing code."
fi
echo "Rules: AGENTS.md (one-line Conventional Commits, no co-authors, PRs to dev, no frontend tests, AI on NVIDIA Brev only)."
exit 0
