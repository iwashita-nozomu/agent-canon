---
name: algorithm-flowchart
description: "Use when rendering JIT-canonical IR records, generated Lean evidence modules, and theorem-graph proof overlays into Mermaid block charts that show the implemented iterative algorithm and proof state."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:algorithm-flowchart -->
<!-- canonical: agents/skills/algorithm-flowchart.md sha256=6e99bf8c83d68979f2a3ce953ccb1a91121223d85a13e96d0da398d0ec703b61 -->
<!-- route: agents/skills/catalog.yaml#skill:algorithm-flowchart.routing digest=001ffb5e2268a4a6346a65a37bc263026b195ce4a5c38feb53cda4a302fcb333 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:algorithm-flowchart digest=0b0214c266a54b45eb61a3431da0acee078a49baf011ed1abe598ef193e0ca5d -->
<!-- commands: agents/skills/catalog.yaml#skill:algorithm-flowchart.tool_commands digest=c83fdc6fbbae04f8659c14d007cce9a41a8cdbefd91e1e61f994680ee507f427 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/algorithm-flowchart.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# algorithm-flowchart

## Canonical Skill

Canonical workflow and policy: [algorithm-flowchart](../../../agents/skills/algorithm-flowchart.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-flowchart --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `c83fdc6fbbae04f8659c14d007cce9a41a8cdbefd91e1e61f994680ee507f427`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
