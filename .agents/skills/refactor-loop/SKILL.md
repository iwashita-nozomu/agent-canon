---
name: refactor-loop
description: "Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:refactor-loop -->
<!-- canonical: agents/skills/refactor-loop.md sha256=af5d3c47e1a5266fcbb38cb58314e547344cef41e3afe9134c94c0c04117b56b -->
<!-- route: agents/skills/catalog.yaml#skill:refactor-loop.routing digest=2fb076b8062b21194ce598f2396fd841cb7e932f04f5429e229f8001d095c0f3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:refactor-loop digest=c2075a67d124d4b7aec3dfd31d2d9cd2ab181bb53adaaff8a752e614c9f5fe72 -->
<!-- commands: agents/skills/catalog.yaml#skill:refactor-loop.tool_commands digest=a9d49937251e18e25631807d7668e425f481a301bbe0f01dd05a624365bea9fe -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/refactor-loop.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# refactor-loop

## Canonical Skill

Canonical workflow and policy: [refactor-loop](../../../agents/skills/refactor-loop.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill refactor-loop --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `a9d49937251e18e25631807d7668e425f481a301bbe0f01dd05a624365bea9fe`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
