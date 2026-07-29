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
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-module-change --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
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
   When the parent packet proves independent replaceable responsibilities with disjoint
   write scope, dependency/merge order, validation route, and reviewer ownership, the
   parent may explicitly select `prepare --placement workspace` even when vendor is
   clean. That typed fresh route creates only the computed
   `workspace/<topic-slug>/<module-basename>` clone from latest `origin/main`, and
   refuses an existing local or remote task branch. A continuation must use the separate
   `--placement workspace-continuation` route; the fresh route does not continue implicitly.
   Neither route creates a parent clone or a compatibility path.
1. For dependency source recovery on corrupted state, wrong write target, merge-conflict
   failure, or unexpected delta, do not reverse patch/restore. Rebuild from
   `origin/main` clean checkout, re-apply intended topic commits only, and
   reopen a successor branch/PR if unmaterialized diff remains.
1. Use `cleanup` as a dry-run first. Apply deletion only with the exact expected clone path and the required same-command authority environment; its remote reconstructibility gate is independent of PR/pin/root-sync state.
1. If a parent update command proposes to preserve or merge dirty vendor source
   state, stop. Use the independent clone only through the typed workspace route
   or the decision table's dirty fallback; otherwise use the typed repair/rebuild
   route. Do not add a compatibility or fallback topology.
