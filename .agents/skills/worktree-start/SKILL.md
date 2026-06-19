---
name: worktree-start
description: Legacy cleanup only. Use when inspecting or retiring stale WORKTREE_SCOPE.md/action-log state; do not use to create, recreate, resume, or move work into a git worktree.
---
<!--
@dependency-start
contract skill
responsibility Documents Worktree Start for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Worktree Start

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-start --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/worktree-start.md`.
1. Do not create a new `git worktree`, do not resume a stale worktree as the task workspace, and do not treat `WORKTREE_SCOPE.md` as scope authority for new work.
1. Read `notes/guardrails/README.md` and `notes/failures/README.md` before cleanup so known avoid patterns and recent failures are in scope.
1. Run `python3 tools/agent_tools/worktree_scope_lint.py --current` only to diagnose stale `WORKTREE_SCOPE.md` state in the current checkout.
1. Run `git status --short --branch` and `git worktree list --porcelain` to inventory existing worktrees; do not add or switch to another worktree.
1. When stale worktrees exist or the resumed state is unclear, run `bash tools/docs/check_worktree_scopes.sh`.
1. Record dirty state, stale scope, conflict risk, and carry-over decisions in the current checkout run-local `work_log.md`; switch to `worktree-health` if cleanup or drift review is needed.
