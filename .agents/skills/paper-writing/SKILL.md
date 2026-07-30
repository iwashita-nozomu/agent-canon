---
name: paper-writing
description: "Use when drafting a submission paper, thesis chapter, or other paper-style manuscript that needs section contracts, citation-evidence review, notation review, and logic-gap review."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:paper-writing -->
<!-- canonical: agents/skills/paper-writing.md sha256=c17997237107186c92e971982e170cb8fd0e054cd37688899db76e6c7b5b9433 -->
<!-- route: agents/skills/catalog.yaml#skill:paper-writing.routing digest=6abba85f3398bed7a914399c09a626713f6f44ca6730b0364fdc3c59d995a8cf -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:paper-writing digest=b71071d06cf7349ee9c566290092330c73730eb55d25a01fd5c70a637e832d8e -->
<!-- commands: agents/skills/catalog.yaml#skill:paper-writing.tool_commands digest=b18e1763f06bdfc45193c7cb5a8b967a7664c499e501d6d06031448c4ab8d052 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/paper-writing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# paper-writing

## Canonical Skill

Canonical workflow and policy: [paper-writing](../../../agents/skills/paper-writing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill paper-writing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `b18e1763f06bdfc45193c7cb5a8b967a7664c499e501d6d06031448c4ab8d052`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
