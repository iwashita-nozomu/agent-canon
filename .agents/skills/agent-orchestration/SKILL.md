---
name: agent-orchestration
description: "Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-orchestration -->
<!-- canonical: agents/skills/agent-orchestration.md sha256=69511390ae60bfe1bf47f41ac91bcd79803b3ffda8d0134b19790e426f54c9d7 -->
<!-- route: agents/skills/catalog.yaml#skill:agent-orchestration.routing digest=3f8c23709a63eb8c7af65da6ba22becbfb9edb77c7320080d8b955bcf1c49b89 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-orchestration digest=cb5ffbaa6b1fff3996a1c6e7c8320778a62a50162a4e53f4db6db1c855462075 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-orchestration.tool_commands digest=4749b7d0041bd03255862252ecb141a7c80044a502caeb3341d90e9e09e9e55c -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/agent-orchestration.md
@dependency-end
-->

# agent-orchestration

## Canonical Skill

Canonical workflow and policy: [agent-orchestration](../../../agents/skills/agent-orchestration.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text`; schema `skill_tool_commands.v2`, digest: `4749b7d0041bd03255862252ecb141a7c80044a502caeb3341d90e9e09e9e55c`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
