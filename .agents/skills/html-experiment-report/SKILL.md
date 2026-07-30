---
name: html-experiment-report
description: "Use when producing a browser-readable HTML experiment or Eval report; first decide the primary figure, then plan and run an evidence-backed report renderer while keeping domain authority in the original tool."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:html-experiment-report -->
<!-- canonical: agents/skills/html-experiment-report.md sha256=810b7a5f1496021f22dc1c4fc9b277d6f60bb9921900989867ce59b8a4f4e247 -->
<!-- route: agents/skills/catalog.yaml#skill:html-experiment-report.routing digest=a75d0c6166dc6a7b942ebfe7604829bc9f8f0147b1a9a0a6e3e4d17d865a21d0 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:html-experiment-report digest=f7e55f5767b4e397ecfeceafe13eda8ed9b765a857b29563e6a3bb773c4ba21e -->
<!-- commands: agents/skills/catalog.yaml#skill:html-experiment-report.tool_commands digest=f14dcd803384868dc064fa6905260d8778937cd111fdbbeafd0b2f9a638e0593 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/html-experiment-report.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# html-experiment-report

## Canonical Skill

Canonical workflow and policy: [html-experiment-report](../../../agents/skills/html-experiment-report.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill html-experiment-report --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `f14dcd803384868dc064fa6905260d8778937cd111fdbbeafd0b2f9a638e0593`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
