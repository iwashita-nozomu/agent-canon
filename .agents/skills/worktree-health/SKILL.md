---
name: worktree-health
description: Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness.
---
<!--
@dependency-start
contract skill
responsibility Documents Worktree Health for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Worktree Health

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-health --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/worktree-health.md`.
1. Read `reports/agents/.active_run`, `task_authority.yaml`, and `team_manifest.yaml` before judging current checkout write authority.
1. Open `WORKTREE_SCOPE.md` and any legacy worktree action log as cleanup evidence only; do not treat them as scope authority for new work.
1. Run `python3 tools/agent_tools/worktree_scope_lint.py --current` only when legacy cleanup is in scope.
1. Check `git status --short --branch`, `git diff --name-only`, and `git worktree list --porcelain`.
1. Treat `git branch --show-current` and `git worktree list --porcelain` as diagnostics; branch/worktree creation is routed by `agents/canonical/CODEX_WORKFLOW.md` Branch Reuse Default and `branch_worktree_guard.py`, while this skill checks only the recorded `branch_creation_reason=<reason>` or `worktree_creation_reason=<reason>` evidence.
1. Re-read `notes/guardrails/README.md` and `notes/failures/README.md` when drift, cleanup, or carry-over risk is not obvious.
1. Run `bash tools/docs/check_worktree_scopes.sh` when legacy drift or stale worktrees are possible.
1. Check task-authority drift, runtime output drift, carry-over readiness, and cleanup readiness before continuing or deleting a worktree.
