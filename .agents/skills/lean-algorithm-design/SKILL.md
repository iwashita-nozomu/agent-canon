---
name: lean-algorithm-design
description: "Use when an algorithm should be designed and checked in Lean before production implementation; models candidate algorithms independently of existing code paths, proves or refutes convergence, stopping, certificate, filter/restoration, and inner-solver contracts, then hands a checked design contract to implementation or implementation-derived proof workflows."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:lean-algorithm-design -->
<!-- canonical: agents/skills/lean-algorithm-design.md sha256=982f62d5b1cc384c71b2dd3a75ce58b78442ebcb740b7f73631d60a333faeeaf -->
<!-- route: agents/skills/catalog.yaml#skill:lean-algorithm-design.routing digest=5edb27b25833419ae869d230f09c139f295a28ea19d91a1460b6e607f8ac3f2f -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:lean-algorithm-design digest=bc6dd72981e8a98f4a593452ecf0e54ecba92c74b7a65ceb51ac776a9a944a72 -->
<!-- commands: agents/skills/catalog.yaml#skill:lean-algorithm-design.tool_commands digest=5f6d285786edee318e075ef39b3ae369c10b4a4d3f6733381fa800a9ddf277ae -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/lean-algorithm-design.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# lean-algorithm-design

## Canonical Skill

Canonical workflow and policy: [lean-algorithm-design](../../../agents/skills/lean-algorithm-design.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill lean-algorithm-design --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `5f6d285786edee318e075ef39b3ae369c10b4a4d3f6733381fa800a9ddf277ae`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
