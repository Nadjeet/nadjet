---
name: review-pr
description: Independently review a pull request against its issue and the PRD, fix real gaps with commits on the PR branch, re-validate until the issue is truly satisfied, then stop for the user's CI confirmation before merging into dev, closing the linked issue and deleting the branch. Use only when the user runs /review-pr <number>.
argument-hint: <pr-number>
disable-model-invocation: true
model: claude-opus-5-5
---

# /review-pr $ARGUMENTS

Review PR **#$ARGUMENTS** as an independent senior engineer, fix what is wrong, and drive it
to a state that genuinely satisfies its issue. Follow `AGENTS.md` at all times.

## 0. Preflight

```bash
gh auth status && git fetch origin --prune
git status --porcelain     # pre-existing changes are not yours: never touch them
gh pr view $ARGUMENTS --json number,state,isDraft,baseRefName,headRefName,headRepositoryOwner,author,title,url
```

- Stop if the PR is closed/merged, its base is not `dev`, or its head is in a fork you cannot
  push to; report and ask.
- If the working tree has unrelated changes, review in a worktree:
  `git worktree add --detach ../nadjet-pr-$ARGUMENTS origin/dev`, then run `gh pr checkout $ARGUMENTS`
  inside it.

## 1. Understand what was supposed to be built

```bash
gh pr view $ARGUMENTS --comments --json title,body,commits,files,closingIssuesReferences,reviews,comments
gh pr diff $ARGUMENTS
gh issue view <linked-issue> --comments
```

- Rebuild the expected behaviour **from the issue, its comments and the PRD requirement IDs**,
  not from the PR description. Write the acceptance criteria checklist yourself.
- If no issue is linked, ask the user which issue it implements before going further.

## 2. Check out and investigate independently

```bash
gh pr checkout $ARGUMENTS
```

- Read every changed file in full, plus the code around it (`Explore` subagent for callers,
  contracts, migrations, tests and docs that should have changed but did not).
- Use the `researcher` subagent to verify library/API usage against official docs for the
  locked versions when correctness depends on it.
- Use the `verifier` subagent for a second, independent pass on the acceptance criteria.

## 3. Review checklist

- **Correctness:** every acceptance criterion implemented; edge cases; error handling;
  concurrency/async; time zones; idempotency; data validation at boundaries.
- **Patterns & skills:** the change follows the existing module layout and conventions of its
  area (see `/implement-issue` step 3) and the relevant installed skills' guidance.
- **Architecture:** fits the repo structure and `docs/11` decisions; no needless abstraction or
  dependency; contracts regenerated (`make check-contracts`); migrations reversible and based
  on the latest `origin/dev` revision (exactly one Alembic head: `scripts/check-migrations.sh`).
- **Security & privacy:** no secrets; input validation; authz where relevant; no PII in logs;
  Brev-only AI rule; licence rules (PRD D-06).
- **Integrity:** no fabricated detections, random values or hardcoded AI results outside tests.
- **Tests:** non-frontend changes have meaningful unit and integration tests that would fail
  without the change; **no frontend tests exist**; no skipped/xfailed shortcuts.
- **Docs & config:** README/AGENTS/docs/.env.example/PRD updated when behaviour changed.
- **Commits:** one-line Conventional Commits, no co-authors, nothing unrelated.
- **Regressions:** run the full validation below on the PR branch.

## 4. Fix real gaps

- Fix what is genuinely wrong or missing (not style preferences already allowed by the
  linters). Add missing tests and docs.
- Commit each fix as a one-line Conventional Commit, no co-authors, then push to the PR branch:

```bash
git commit -m "fix(api): reject sms with unknown incident code"
git push            # never --force
```

## 5. Validate, then repeat until satisfied

```bash
make format && make lint && make typecheck && make check-contracts && make test
make build          # when build config, dependencies or the web app changed
```

Loop steps 3–5 until every acceptance criterion is met with evidence and all checks pass.

## 6. Report and STOP at the CI gate

- Post a review comment on the PR (`gh pr comment $ARGUMENTS --body-file <file>`) with: the
  acceptance-criteria checklist and evidence, issues found, fixes pushed (commit SHAs),
  validation results, and anything left for a human.
- Tell the user the PR is ready and **ask them to confirm that GitHub CI is green**.
- **Stop here.** Do not merge, close or delete anything until the user explicitly confirms in chat.

## 7. After the user confirms CI is green

1. Re-check: `gh pr checks $ARGUMENTS` must show all checks passing. If not, report and stop.
2. Verify relationships: the issue(s) to close are in the PR's `closingIssuesReferences`
   (or explicitly linked in its body), and the branch to delete is the PR's `headRefName`
   (never `dev` or `main`).
3. Merge into `dev`, keeping the one-line commits, and delete the branch remotely:

```bash
gh pr merge $ARGUMENTS --rebase --delete-branch
```

4. Close each linked issue that is still open (GitHub only auto-closes on the default branch):

```bash
gh issue close <issue> --comment "Done in #$ARGUMENTS (merged into dev)."
```

5. Clean up locally: `git switch dev && git pull --ff-only`, then
   `git branch -d <headRefName>` (only if it still exists) and remove any review worktree.
6. Report what was merged, closed and deleted.

If the user asks to close **without merging**, use `gh pr close $ARGUMENTS --delete-branch`
instead of step 3 and confirm before deleting the local branch.
