---
name: dependency-module-change
description: Use when a dependency source change, topic workspace branch clone, module workspace projection, or reconstructibility-based clone cleanup is required.
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
1. Classify the work as source-edit, pin/update, or read-only. Create/reuse a topic workspace clone only for an owner-evidenced source edit, and require `--topic`, `--module`, `--branch`, and `--owner-evidence`; use `--parent-branch` for a pin PR branch.
1. In parent mode, never edit `vendor/<module>` as a source branch. Use `python3 tools/agent_tools/dependency_module_change.py prepare --topic <topic> --module <module> --branch <branch> --owner-evidence <file>` for the exact topic membership and `workspace` for the parent-local projection.
1. Use `cleanup` as a dry-run first. Apply deletion only with the exact expected clone path and the required same-command authority environment; its remote reconstructibility gate is independent of PR/pin/root-sync state.
1. If a parent update command proposes to preserve or merge dirty vendor source state, stop and route the source change to the independent clone. Do not add a compatibility or fallback topology.
