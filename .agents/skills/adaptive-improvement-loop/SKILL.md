---
name: adaptive-improvement-loop
description: "Use when experiments, research, tuning, and iterative code improvement must be managed as one backlog-driven agile outer loop."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:adaptive-improvement-loop -->
<!-- canonical: agents/skills/adaptive-improvement-loop.md sha256=1069d73a5c48a7f85a25a0a41a2a18e222af6d829d2fd17ad0acf9155118a7a0 -->
<!-- route: agents/skills/catalog.yaml#skill:adaptive-improvement-loop.routing digest=23e1cbdbd8e61d9e73fbaebf2a031960ab1ff5f4f399f984b824432580cfe972 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:adaptive-improvement-loop digest=0faf8f774b0915b7435bd750444cdcff6ff3055e642e560595a2a5b8143e027a -->
<!-- commands: agents/skills/catalog.yaml#skill:adaptive-improvement-loop.tool_commands digest=25b10c7b174c855dc8fd3fb15e35d6a573e3b5dbcd397d67cffc2a57585706c6 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/adaptive-improvement-loop.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# adaptive-improvement-loop

## Canonical Skill

Canonical workflow and policy: [adaptive-improvement-loop](../../../agents/skills/adaptive-improvement-loop.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill adaptive-improvement-loop --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `25b10c7b174c855dc8fd3fb15e35d6a573e3b5dbcd397d67cffc2a57585706c6`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
