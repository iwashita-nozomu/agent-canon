---
name: worktree-start
description: Use this skill when creating, recreating, or resuming a worktree and you need to lock scope, action-log paths, carry-over targets, and kickoff checks before editing.
---
<!--
@dependency-start
responsibility Documents Worktree Start for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Worktree Start

1. Read `agents/skills/worktree-start.md`.
1. Read `notes/guardrails/README.md` and `notes/failures/README.md` before editing so known avoid patterns and recent failures are in scope.
1. Run `bash tools/worktree_start.sh <branch-name> [worktree-path]` for new worktrees or `python3 tools/agent_tools/worktree_start.py --current` when resuming one.
1. Refresh `WORKTREE_SCOPE.md` before the first edit. Fill concrete branch, path, editable directories, runtime outputs, references, carry-over targets, and required checks.
1. Run `python3 tools/agent_tools/worktree_scope_lint.py --current` after refreshing the scope and fix placeholders or stale kickoff fields.
1. If this worktree owns an experiment topic, run `python3 tools/experiments/sync_experiment_registry_context.py --topic <topic> --branch <branch>` so `active_branch` and related scope metadata are current.
1. Create or update the action log from `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`, then append the first kickoff entry before changing code or docs.
1. If the branch will survive multiple sessions or needs handoff, create or update `notes/branches/<branch_topic>.md`.
1. Run `git status --short --branch` and `git worktree list --porcelain`.
1. When multiple worktrees exist or the resumed state is unclear, run `bash tools/docs/check_worktree_scopes.sh`.
1. If you see dirty state, stale scope, or conflict risk, record it in the action log before editing and switch to `worktree-health` if cleanup or drift review is needed.
