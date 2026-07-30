---
name: dependency-module-change
description: "Use when a dependency source change, topic branch clone, or reconstructibility-based clone cleanup is required."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-module-change -->
<!-- canonical: agents/skills/dependency-module-change.md sha256=a78e6e956eea291fc69795b309c214a839b6db38eb9b63b10ff73c069db70978 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-module-change.routing digest=480ca2a53bcef269adb16b237607f3d3be00c07de3ab35c544a8a6351c2c7705 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-module-change digest=73f5b1d62b4728d1bfe316aefa66846e46b69218f5bece3c11ac8a4cad8d1e12 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-module-change.tool_commands digest=1e039b7e06b6ad59fbbf4d6b9d7b6836e5e5f81a7bcf9316f992573d6a00afa4 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/dependency-module-change.md
@dependency-end
-->

# dependency-module-change

## Canonical Skill

Canonical workflow and policy: [dependency-module-change](../../../agents/skills/dependency-module-change.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-module-change --format text`; schema `skill_tool_commands.v2`, digest: `1e039b7e06b6ad59fbbf4d6b9d7b6836e5e5f81a7bcf9316f992573d6a00afa4`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
