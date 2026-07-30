---
name: literature-survey
description: "Use when a task needs paper search, prior-art mapping, contradictory-source hunting, or a reusable bibliography."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:literature-survey -->
<!-- canonical: agents/skills/literature-survey.md sha256=4ea0bcfd04a7db46709cc7aafb5824601ae1c6f080e4f70e6b6b716d2c90c6a4 -->
<!-- route: agents/skills/catalog.yaml#skill:literature-survey.routing digest=d4f4cf4a983780461a4267d1cbd74b267b0b2595afe2e206796f068577da7df3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:literature-survey digest=fa83085b0c4dcab7ecbec02f8fc20fadb3a52c3e8858462177b53cbe99d5b90f -->
<!-- commands: agents/skills/catalog.yaml#skill:literature-survey.tool_commands digest=d761bb4dee3c6bea232662130f7d3613733c1ed4b45d0f61b10e9f6e07f65d00 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/literature-survey.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# literature-survey

## Canonical Skill

Canonical workflow and policy: [literature-survey](../../../agents/skills/literature-survey.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill literature-survey --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `d761bb4dee3c6bea232662130f7d3613733c1ed4b45d0f61b10e9f6e07f65d00`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
