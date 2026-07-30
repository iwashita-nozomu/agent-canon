---
name: wiki-publication
description: "Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:wiki-publication -->
<!-- canonical: agents/skills/wiki-publication.md sha256=9f83f747726d605400e4180da5f8d68d5828a3af47797f29870cfb40fef52d8c -->
<!-- route: agents/skills/catalog.yaml#skill:wiki-publication.routing digest=5dad8bcc880ca607eee2a53db930c5162f3a0c1f49169bbaed2ea5e15a559909 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:wiki-publication digest=99168c55688c0e24c5211e38865ad558a1d1dfcc073db7941116a921456eaf9f -->
<!-- commands: agents/skills/catalog.yaml#skill:wiki-publication.tool_commands digest=0118c997417cea67c30523c8499a84903fe08a8167edfa1a08dad876ecf124a6 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/wiki-publication.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# wiki-publication

## Canonical Skill

Canonical workflow and policy: [wiki-publication](../../../agents/skills/wiki-publication.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill wiki-publication --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `0118c997417cea67c30523c8499a84903fe08a8167edfa1a08dad876ecf124a6`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
