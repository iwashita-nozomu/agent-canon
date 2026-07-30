---
name: oop-type-design
description: "Use before implementation to define language-neutral OOP/type contracts, responsibility boundaries, and explicit capability-owned design packets."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:oop-type-design -->
<!-- canonical: agents/skills/oop-type-design.md sha256=f66ca06f84062514db0f0bee00dd233bef080f2cfde073f04f0571cd15af72c0 -->
<!-- route: agents/skills/catalog.yaml#skill:oop-type-design.routing digest=6ce93686d6bc10719b32c72429e99c7e24edb207cce42d19bef8814de3e27efe -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:oop-type-design digest=06f18f43f9a0adccc3656e2ee451a055fa2f2ff4b9913f42e2648d1c54991605 -->
<!-- commands: agents/skills/catalog.yaml#skill:oop-type-design.tool_commands digest=7d33462104c351f2b1e8a6c14d0601750e7d5252eeb8842a416e39e24317833f -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/oop-type-design.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# oop-type-design

## Canonical Skill

Canonical workflow and policy: [oop-type-design](../../../agents/skills/oop-type-design.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill oop-type-design --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `7d33462104c351f2b1e8a6c14d0601750e7d5252eeb8842a416e39e24317833f`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
