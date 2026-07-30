---
name: algorithm-proof-exploration
description: "Use when exploring, refactoring, or choosing an algorithm under proof obligations; builds JIT-canonical IR, lemma dependency graphs, algorithmic blocker frontiers, and algorithm-change guidance before handing terminal proof work to formal-proof-workflow."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:algorithm-proof-exploration -->
<!-- canonical: agents/skills/algorithm-proof-exploration.md sha256=c042790e52d826a43771b85ecf8f8dcb3d4dff01dfb5782f1afd2c4f84d610f8 -->
<!-- route: agents/skills/catalog.yaml#skill:algorithm-proof-exploration.routing digest=285ba77252ed0ac7692425ad9ce43f29404b1c921f112b06d4841ef46d55ad0d -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:algorithm-proof-exploration digest=d9e5685bf1003aafdadeb113773d1418a6c93a5b8b209035f2e328e13280d4df -->
<!-- commands: agents/skills/catalog.yaml#skill:algorithm-proof-exploration.tool_commands digest=56d8454f0b0400e344bac273a1526ac45dbfeeca533652cd21dea4d2334dc078 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/algorithm-proof-exploration.md
@dependency-end
-->

# algorithm-proof-exploration

## Canonical Skill

Canonical workflow and policy: [algorithm-proof-exploration](../../../agents/skills/algorithm-proof-exploration.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-proof-exploration --format text`; schema `skill_tool_commands.v2`, digest: `56d8454f0b0400e344bac273a1526ac45dbfeeca533652cd21dea4d2334dc078`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
