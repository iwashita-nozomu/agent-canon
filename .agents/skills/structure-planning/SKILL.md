---
name: structure-planning
description: "Use when a report, experiment plan, Eval output, presentation storyboard, PPT/deck plan, document, paper, HTML view, or refactor needs a structure contract before prose, rendering, interpretation, follow-up runs, or edits."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:structure-planning -->
<!-- canonical: agents/skills/structure-planning.md sha256=e6dc1049dfabff9b68e07e20c658ca04dac51a2b067207fffaa76ecc4e1a532f -->
<!-- route: agents/skills/catalog.yaml#skill:structure-planning.routing digest=a85e0ff9aec22048442d3faf8708dd83d8544eda291130e724f733a714b43ec8 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:structure-planning digest=63503ea8cdb8b6e9cdfa8223fca912882274bc6fdd63e93229706b9bf2ed2c09 -->
<!-- commands: agents/skills/catalog.yaml#skill:structure-planning.tool_commands digest=1761fc61e0b6fc675ed6da769512e5c25e61661a3ddb21b33b4dfce59bda3256 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/structure-planning.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# structure-planning

## Canonical Skill

Canonical workflow and policy: [structure-planning](../../../agents/skills/structure-planning.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill structure-planning --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `1761fc61e0b6fc675ed6da769512e5c25e61661a3ddb21b33b4dfce59bda3256`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
