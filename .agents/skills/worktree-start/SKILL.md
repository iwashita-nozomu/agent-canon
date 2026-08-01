---
name: worktree-start
description: "Legacy cleanup only. Use when inspecting or retiring stale WORKTREE_SCOPE.md/action-log state; do not use to create, recreate, resume, or move work into a git worktree."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"8db7b44fd6c0906f4b762a3571b03fc8023f6e300f2f88f4313009c8f64b00f0"} -->

<!--
@dependency-start
contract skill
responsibility Exposes worktree-start for runtime discovery.
upstream design ../../../agents/skills/worktree-start.md owner
@dependency-end
-->

# worktree-start

## Canonical Skill

Canonical workflow and policy: [worktree-start](../../../agents/skills/worktree-start.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-start --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
