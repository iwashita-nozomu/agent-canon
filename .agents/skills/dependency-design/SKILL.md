---
name: dependency-design
description: "Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-design -->
<!-- canonical: agents/skills/dependency-design.md sha256=94f31aef4da72013fdb9ac61c5407f25546a5dc612fa743d5925322812441e80 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-design.routing digest=fd5d2c3a0fa886708e92ae247efd24e15b5f15d0aea9c1d07ee58fa49755de74 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-design digest=102ef25d019c6a191262ebeef4c65533b17b6a9680b60df32d2a7c411c5817a2 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-design.tool_commands digest=4be4c501784a9d8ab5b0d475c74a168b4ef26e321b830df39729435a5923cd0b -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/dependency-design.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# dependency-design

## Canonical Skill

Canonical workflow and policy: [dependency-design](../../../agents/skills/dependency-design.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `4be4c501784a9d8ab5b0d475c74a168b4ef26e321b830df39729435a5923cd0b`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
