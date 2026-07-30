---
name: agent-learning
description: "Use when agent-side working philosophy, interaction lessons, task retrospectives, repeated routing misses, missed skill invocation, or recurrence-prevention feedback should be logged without mixing them into user preferences."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-learning -->
<!-- canonical: agents/skills/agent-learning.md sha256=b9aebad7f6ae5825f3a5ea32ad35bee46e879c4e712667d3e7b3c3cf9c0a7e78 -->
<!-- route: agents/skills/catalog.yaml#skill:agent-learning.routing digest=7d92634fcce7234f7eb340873ccb4d93f7e920dcba6cdbe0db55d16ae045d015 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-learning digest=d119e106e2ec69ebe058ffa24352ab745c427743fa2822df9513a021cb6b11e2 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-learning.tool_commands digest=67315c755e9f80cd7fbec3cbc876482fc1ea0d58e46e56bc6bf0b746bba93472 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/agent-learning.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# agent-learning

## Canonical Skill

Canonical workflow and policy: [agent-learning](../../../agents/skills/agent-learning.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-learning --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `67315c755e9f80cd7fbec3cbc876482fc1ea0d58e46e56bc6bf0b746bba93472`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
