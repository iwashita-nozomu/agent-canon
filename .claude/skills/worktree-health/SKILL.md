---
name: worktree-health
description: Use this skill to review current worktree scope, drift, and cleanup readiness.
---
<!--
@dependency-start
responsibility Documents Worktree Health for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Worktree Health

1. Read `agents/skills/worktree-health.md`.
1. Open `WORKTREE_SCOPE.md` and the current worktree action log before reviewing git state.
1. Run `python3 tools/agent_tools/worktree_scope_lint.py --current` to catch placeholder fields or stale kickoff metadata.
1. Check `git status --short --branch`, `git diff --name-only`, and `git worktree list --porcelain`.
1. Re-read `notes/guardrails/README.md` and `notes/failures/README.md` when drift, cleanup, or carry-over risk is not obvious.
1. Run `bash tools/docs/check_worktree_scopes.sh` when drift or stale worktrees are possible.
1. Check scope drift, runtime output drift, carry-over readiness, and cleanup readiness before continuing or deleting a worktree.
