---
name: task-routing
description: "Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:task-routing -->
<!-- canonical: agents/skills/task-routing.md sha256=be32626dab962267dc9229f93d19a4a1abec015c4ccf80b3fe37eaefd4801938 -->
<!-- route: agents/skills/catalog.yaml#skill:task-routing.routing digest=8d98862013a741d63075e56acdedc1bc49afa889b0dd6807830516ccd47ff90e -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:task-routing digest=728ab411a06957e0dfe7ba3fdc10b3e4a2816dad67a8dcc7ba9d2528b12be33e -->
<!-- commands: agents/skills/catalog.yaml#skill:task-routing.tool_commands digest=f105f5d94cf9b380ffd2c41f7690ef4d1519cd1cc7d2993ea53543a9ab328898 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/task-routing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# task-routing

## Canonical Skill

Canonical workflow and policy: [task-routing](../../../agents/skills/task-routing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill task-routing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `f105f5d94cf9b380ffd2c41f7690ef4d1519cd1cc7d2993ea53543a9ab328898`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
