---
name: tool-finding-report
description: "Use when running tools, checkers, hooks, static analysis, or structural analyzers to find problems, preserve raw and structured full finding artifacts, mechanically rank every finding, and produce a complete finding report for implementation or refactor planning; before/after impact is optional when explicitly requested."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:tool-finding-report -->
<!-- canonical: agents/skills/tool-finding-report.md sha256=d72485e69bc2af8f11ab3e9fef38fb1d72a125b7b9ff05ab709d6e87a97a4c20 -->
<!-- route: agents/skills/catalog.yaml#skill:tool-finding-report.routing digest=c4efc1f6d5c496198e24285312873ccf59fee23f28859f6165573e2610b4de5c -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:tool-finding-report digest=73a0440bb18fb73e90cbe91c224e13749583a0c5427287daf292f3053ebe7c65 -->
<!-- commands: agents/skills/catalog.yaml#skill:tool-finding-report.tool_commands digest=2ebcc7500ef166476ebf640526aa1d823c35e88ccd244c2e210a3aee76bf0052 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/tool-finding-report.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# tool-finding-report

## Canonical Skill

Canonical workflow and policy: [tool-finding-report](../../../agents/skills/tool-finding-report.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill tool-finding-report --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `2ebcc7500ef166476ebf640526aa1d823c35e88ccd244c2e210a3aee76bf0052`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
