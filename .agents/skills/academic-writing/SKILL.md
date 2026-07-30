---
name: academic-writing
description: "Use when drafting a paper, thesis chapter, scholarly note, or other academic document that needs mandatory multi-agent review for notation, logic, and reader flow."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:academic-writing -->
<!-- canonical: agents/skills/academic-writing.md sha256=0b9d0e6901cc0a67bc3c2181c378ba1fb0f0a3430770fa19a1fa3e8c99cb2337 -->
<!-- route: agents/skills/catalog.yaml#skill:academic-writing.routing digest=ca10bf6d75f42cd4327f5f00eb4a2d4bd60d989e5e15e07e1277226fff1a36cc -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:academic-writing digest=4cda45473cbe5fe4639378efbbac6b3b38a044c67ea77a6b9995a427c471c1a7 -->
<!-- commands: agents/skills/catalog.yaml#skill:academic-writing.tool_commands digest=561590ebe2edf789760dc83d3d374325ea550408192cafc55d4f7022baabc102 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/academic-writing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# academic-writing

## Canonical Skill

Canonical workflow and policy: [academic-writing](../../../agents/skills/academic-writing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill academic-writing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `561590ebe2edf789760dc83d3d374325ea550408192cafc55d4f7022baabc102`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
