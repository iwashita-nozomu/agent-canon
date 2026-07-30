---
name: agent-eval-accumulation
description: "Use when accumulated AgentCanon eval evidence is missing, stale, or failing; runs registered eval producers, validates eval family accumulation, and stores evidence through the log archive instead of hand-writing reports."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-eval-accumulation -->
<!-- canonical: agents/skills/agent-eval-accumulation.md sha256=42c75a12dac93c1e51668f11ff7138928339516ab8fb8c8aee8cf18b77fc8a1e -->
<!-- route: agents/skills/catalog.yaml#skill:agent-eval-accumulation.routing digest=82fd113d81262b8d7b75a47957fd861829b51a5fd467126ed3f04dc60c578b70 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-eval-accumulation digest=2ba8693a0245e679ab9fdb4e0e25448a861704470bc21c216894baa6031a5a83 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-eval-accumulation.tool_commands digest=aeb8ee6c2a167717f9c8fe0a7e6ac8d74aad12f9c5ee9e911ea66780dd605df0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/agent-eval-accumulation.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../agents/skills/agent-eval-accumulation.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-eval-accumulation --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `aeb8ee6c2a167717f9c8fe0a7e6ac8d74aad12f9c5ee9e911ea66780dd605df0`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
