---
name: prose-reasoning-graph
description: "Use when existing prose should be converted into a SQLite-backed structure graph, diagnosed for discourse/argument/evidence/experiment gaps, explained in natural language, and handed off to writing or review skills with split/merge/bridge/reorder rewrite packets."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:prose-reasoning-graph -->
<!-- canonical: agents/skills/prose-reasoning-graph.md sha256=45728c582df1b39f818e2e6ac5bf2a56cbc2278c036304f176dd5be8f1cdb508 -->
<!-- route: agents/skills/catalog.yaml#skill:prose-reasoning-graph.routing digest=b750d3bf38d9fd351ec65b811d9c33ede2668d50c735670f53c15c5ce611df38 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:prose-reasoning-graph digest=d56c3955f3c177216a9feba7502f8ae837e83c92189473870a1fa55ed96e03d7 -->
<!-- commands: agents/skills/catalog.yaml#skill:prose-reasoning-graph.tool_commands digest=d334723afe2c0a97631f68b228b04c097dcacbccadfcb1d058344548e4470242 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/prose-reasoning-graph.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# prose-reasoning-graph

## Canonical Skill

Canonical workflow and policy: [prose-reasoning-graph](../../../agents/skills/prose-reasoning-graph.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill prose-reasoning-graph --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `d334723afe2c0a97631f68b228b04c097dcacbccadfcb1d058344548e4470242`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
