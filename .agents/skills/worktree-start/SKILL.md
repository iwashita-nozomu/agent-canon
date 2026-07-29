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
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-start --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->


1. Read `agents/skills/worktree-start.md`.
1. Do not create a new `git worktree`, do not resume a stale worktree as the task workspace, and do not treat `WORKTREE_SCOPE.md` as scope authority for new work.
1. Read `notes/guardrails/README.md` and `notes/failures/README.md` before cleanup so known avoid patterns and recent failures are in scope.
1. Run `python3 tools/agent_tools/worktree_scope_lint.py --current` only to diagnose stale `WORKTREE_SCOPE.md` state in the current checkout.
1. Run `git status --short --branch` and `git worktree list --porcelain` to inventory existing worktrees; do not add or switch to another worktree.
1. When stale worktrees exist or the resumed state is unclear, run `bash tools/docs/check_worktree_scopes.sh`.
1. Record dirty state, stale scope, conflict risk, and carry-over decisions in the current checkout run-local `work_log.md`; switch to `worktree-health` if cleanup or drift review is needed.
