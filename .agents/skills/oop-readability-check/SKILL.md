---
name: oop-readability-check
description: "Use when the user asks to run the OOP readability checker, SOLID check, OOP check, readability check, produce a mechanical OOP report table, or interpret/prioritize OOP readability results; keep mechanical tool output separate from agent analysis."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:oop-readability-check -->
<!-- canonical: agents/skills/oop-readability-check.md sha256=57d676d84ba9fac2d2c837ee114cf4f711bb8a1b5f4b9d81470e536005e70648 -->
<!-- route: agents/skills/catalog.yaml#skill:oop-readability-check.routing digest=bb3d89ba9d1db9a6007b3cef2601174b6a950c12850b566684639b217be106d1 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:oop-readability-check digest=3ceeae86534bd675b142a2760ae269df6bb49165786fdaa15876921e2db116dd -->
<!-- commands: agents/skills/catalog.yaml#skill:oop-readability-check.tool_commands digest=87503446ed556b99ea7ff95fa0e8be5be859ecd7c43df94df1a20623b6115316 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/oop-readability-check.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# oop-readability-check

## Canonical Skill

Canonical workflow and policy: [oop-readability-check](../../../agents/skills/oop-readability-check.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill oop-readability-check --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `87503446ed556b99ea7ff95fa0e8be5be859ecd7c43df94df1a20623b6115316`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
