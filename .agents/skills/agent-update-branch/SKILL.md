---
name: agent-update-branch
description: "Use when Memory, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-update-branch -->
<!-- canonical: agents/skills/agent-update-branch.md sha256=a3a6696922e35315b2b2b64ea0104a0b106ce42988364d3649a1d61c505aa8c4 -->
<!-- route: agents/skills/catalog.yaml#skill:agent-update-branch.routing digest=4548d2cbdafa14176e2b581c3b38cd0274b8725cc036cd0596d444fef9243293 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-update-branch digest=63a8f40867793c99082c96ae8f6c56737223c1b65b2156de2df6419a774e992f -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-update-branch.tool_commands digest=4048c555120573904834534af72df5a1ebcc841ac67edc44ea92339d1c55e098 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/agent-update-branch.md
@dependency-end
-->

# agent-update-branch

## Canonical Skill

Canonical workflow and policy: [agent-update-branch](../../../agents/skills/agent-update-branch.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-update-branch --format text`; schema `skill_tool_commands.v2`, digest: `4048c555120573904834534af72df5a1ebcc841ac67edc44ea92339d1c55e098`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
