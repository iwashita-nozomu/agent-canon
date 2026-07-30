---
name: result-visualize
description: "Use when designing reusable result visualizations that bind each figure to its exact calculation, coverage, and chart geometry in one contract."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:result-visualize -->
<!-- canonical: agents/skills/result-visualize.md sha256=c34cc9c9716609a99cc71a4337cbe3cc1194db6b8a1ba778bc11a1bee276d9f9 -->
<!-- route: agents/skills/catalog.yaml#skill:result-visualize.routing digest=6f477f0e2de87b70c9ed5eb157a8e4078a8f4a1f0e669bd16a2c6bfada0cfbbd -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:result-visualize digest=f9e28077796907f79bc9c1021ffcf22fcf418870eaca780f8f7e5541118f2f95 -->
<!-- commands: agents/skills/catalog.yaml#skill:result-visualize.tool_commands digest=f95fcc2c038e4ff1a4941f2dc19abaa1376ca3a3871e207184327856992af032 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/result-visualize.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# result-visualize

## Canonical Skill

Canonical workflow and policy: [result-visualize](../../../agents/skills/result-visualize.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill result-visualize --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `f95fcc2c038e4ff1a4941f2dc19abaa1376ca3a3871e207184327856992af032`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
