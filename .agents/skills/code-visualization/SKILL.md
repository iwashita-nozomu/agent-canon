---
name: code-visualization
description: "Sole public visualization owner for code, repository structure, runtime behavior, state, data movement, dependencies, types, proof state, interactive graphs, and document diagrams; builds the complete typed universe and coverage manifest before delegating renderer-only projection."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:code-visualization -->
<!-- canonical: agents/skills/code-visualization.md sha256=5f6d36db19e9e2b7def6611515bb1d77d9958c268ced8241d2044753c82dab30 -->
<!-- route: agents/skills/catalog.yaml#skill:code-visualization.routing digest=ba012b9d0ad5ca234b17c2e7c146b4e302174af6558412ba93b1521a3c80526a -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:code-visualization digest=c55efa485014c1ffdcbc12e5fd00040320b0af1ac612a35d8f42f19513717fbe -->
<!-- commands: agents/skills/catalog.yaml#skill:code-visualization.tool_commands digest=eef8b9f1f9446631c5c1e30c02d95713654c18bcec830c11af78333d64cd8273 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/code-visualization.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# code-visualization

## Canonical Skill

Canonical workflow and policy: [code-visualization](../../../agents/skills/code-visualization.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill code-visualization --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `eef8b9f1f9446631c5c1e30c02d95713654c18bcec830c11af78333d64cd8273`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
