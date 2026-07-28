---
name: dependency-module-change
description: Use when a dependency source change, topic branch clone, or reconstructibility-based clone cleanup is required.
---
<!--
@dependency-start
contract skill
responsibility Routes dependency module changes to the general source-clone policy and lifecycle tool.
upstream design ../../../documents/rule/dependency-module-changes.md generic dependency module change policy
upstream design ../../../agents/skills/catalog.yaml public skill registry and routing metadata
upstream implementation ../../../tools/agent_tools/dependency_module_change.py lifecycle tool
@dependency-end
-->

# Dependency Module Change

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-module-change --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `documents/rule/dependency-module-changes.md` as the only detailed policy owner.
   Its [`AgentCanon parent state decision table`](../../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table)
   owns parent state and dirty fallback topic identity; this runtime shim does
   not duplicate that table.
1. Classify the work as source-edit, pin/update, or read-only. Create/reuse a topic workspace clone only for an owner-evidenced source edit, and require `--topic`, `--module`, `--branch`, and `--owner-evidence`; use `--parent-branch` for a pin PR branch.
1. In parent mode, source-edit default route is `vendor/<module>` on a topic-named
   branch. `workspace/<topic-slug>/<module-basename>` fallback is used only when that
   parent vendor checkout is occupied by another topic's dirty state. `main` 上の
   親 vendor は source 編集の開始点とせず、topic branch の作成へ遷移します。
   Parent pin/root projection is a separate pass state: clean `main` with
   submodule worktree `HEAD == :$PREFIX` from the staged index.
1. For dependency source recovery on corrupted state, wrong write target, merge-conflict
   failure, or unexpected delta, do not reverse patch/restore. Rebuild from
   `origin/main` clean checkout, re-apply intended topic commits only, and
   reopen a successor branch/PR if unmaterialized diff remains.
1. Use `cleanup` as a dry-run first. Apply deletion only with the exact expected clone path and the required same-command authority environment; its remote reconstructibility gate is independent of PR/pin/root-sync state.
1. If a parent update command proposes to preserve or merge dirty vendor source
   state, stop. Use the independent clone only when another topic owns that
   dirty checkout; otherwise use the typed repair/rebuild route. Do not add a
   compatibility or fallback topology.
