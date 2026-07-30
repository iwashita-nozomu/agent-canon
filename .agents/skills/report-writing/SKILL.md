---
name: report-writing
description: "Use when drafting or revising reader-facing reports, decision briefs, experiment summaries, presentation narratives, PPT/storyboard plans, or slide-ready visual asset plans from tool, hook, eval, experiment, review, audit, or operational evidence; separates raw-result writeout from report narrative and applies the report quality checklist."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:report-writing -->
<!-- canonical: agents/skills/report-writing.md sha256=559a11831282d6a36730a3fa4763ad26ca0a27d63f171a808fbc4865ff87505b -->
<!-- route: agents/skills/catalog.yaml#skill:report-writing.routing digest=8a09ead0535032817f97eeaec52cbcc6633247161be7ec6b662bb813c2df760d -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:report-writing digest=5f0856a9544815a681d9d1fd9880697fa5926d640024f4e7d5a2287d426e5877 -->
<!-- commands: agents/skills/catalog.yaml#skill:report-writing.tool_commands digest=584b555300bc1b1b01262d515a19d702385e4e50b211158b874e606cb3fc9e97 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/report-writing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# report-writing

## Canonical Skill

Canonical workflow and policy: [report-writing](../../../agents/skills/report-writing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill report-writing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `584b555300bc1b1b01262d515a19d702385e4e50b211158b874e606cb3fc9e97`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
