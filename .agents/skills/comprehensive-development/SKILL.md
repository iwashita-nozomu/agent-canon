---
name: comprehensive-development
description: "Use when a repo-wide task spans code, docs, tools, workflows, and runtime surfaces and needs explicit subagent routing."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:comprehensive-development -->
<!-- canonical: agents/skills/comprehensive-development.md sha256=09f4caa99d3290b9311842592b168d78e4a9d3ba4e608a517bfc58d1d64ba91e -->
<!-- route: agents/skills/catalog.yaml#skill:comprehensive-development.routing digest=c5a6312f47f5551dc5647765befe569ea80e28516cce821a2440eaab3bd83f55 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:comprehensive-development digest=bd430951132f16013dc607063a8beb8b538bf17835b4a427b2f2d03eba973d50 -->
<!-- commands: agents/skills/catalog.yaml#skill:comprehensive-development.tool_commands digest=d76fb141d0f4843ceac353f18f824b1ded4f3600d4a361a45cd481f5a0f2a5a0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/comprehensive-development.md
@dependency-end
-->

# comprehensive-development

## Canonical Skill

Canonical workflow and policy: [comprehensive-development](../../../agents/skills/comprehensive-development.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill comprehensive-development --format text`; schema `skill_tool_commands.v2`, digest: `d76fb141d0f4843ceac353f18f824b1ded4f3600d4a361a45cd481f5a0f2a5a0`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
