---
name: refactor-loop
description: "Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:refactor-loop -->
<!-- canonical: agents/skills/refactor-loop.md sha256=21755d7f6fa239d0cd90acf8672346166e947ab8ade6a62778c3fc4412c61476 -->
<!-- route: agents/skills/catalog.yaml#skill:refactor-loop.routing digest=2fb076b8062b21194ce598f2396fd841cb7e932f04f5429e229f8001d095c0f3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:refactor-loop digest=c2075a67d124d4b7aec3dfd31d2d9cd2ab181bb53adaaff8a752e614c9f5fe72 -->
<!-- commands: agents/skills/catalog.yaml#skill:refactor-loop.tool_commands digest=def1fc5effa57453bbf898dee64d5874ba491645eb6e1a7f27f6de7a6c338a1a -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/refactor-loop.md
@dependency-end
-->

# refactor-loop

## Canonical Skill

Canonical workflow and policy: [refactor-loop](../../../agents/skills/refactor-loop.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill refactor-loop --format text`; schema `skill_tool_commands.v2`, digest: `def1fc5effa57453bbf898dee64d5874ba491645eb6e1a7f27f6de7a6c338a1a`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
