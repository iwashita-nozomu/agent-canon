---
name: worktree-start
description: "Legacy cleanup only. Use when inspecting or retiring stale WORKTREE_SCOPE.md/action-log state; do not use to create, recreate, resume, or move work into a git worktree."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"ea51bb7878dd2b616ece5b97f67c253f37b7f09016d1cb25ef088d261d334d30"} -->

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
