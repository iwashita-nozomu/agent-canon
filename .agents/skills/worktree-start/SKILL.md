---
name: worktree-start
description: "Legacy cleanup only. Use when inspecting or retiring stale WORKTREE_SCOPE.md/action-log state; do not use to create, recreate, resume, or move work into a git worktree."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:worktree-start -->
<!-- canonical: agents/skills/worktree-start.md sha256=9a65991d0ac390f6bc064a2255c592186505ef3ecd38537deabf7556ae5b09ec -->
<!-- route: agents/skills/catalog.yaml#skill:worktree-start.routing digest=f9cb6b221d17d0308bd040347c11e94ddab13575ca018a72f23e2020ad098eba -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:worktree-start digest=a3a886ec15c580c1586816563a2dd29fdc3d03db0757a415f63f01309926f73e -->
<!-- commands: agents/skills/catalog.yaml#skill:worktree-start.tool_commands digest=a26b693fc2f90117e305b1f8b7c6b738ee4ff51547912f5389e7df944e4e689b -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/worktree-start.md
@dependency-end
-->

# worktree-start

## Canonical Skill

Canonical workflow and policy: [worktree-start](../../../agents/skills/worktree-start.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-start --format text`; schema `skill_tool_commands.v2`, digest: `a26b693fc2f90117e305b1f8b7c6b738ee4ff51547912f5389e7df944e4e689b`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
