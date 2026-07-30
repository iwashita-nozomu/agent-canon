---
name: long-form-writing
description: "Use as the general explanatory-doc DSL-to-prose adapter for README, workflow, guide, migration, or specification documents whose file responsibility is reader-facing explanation; do not select this skill by text length alone."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:long-form-writing -->
<!-- canonical: agents/skills/long-form-writing.md sha256=8304bd516c962591c98e2976d3539b1eaef2a3a898f945da9bf15611f6d2853e -->
<!-- route: agents/skills/catalog.yaml#skill:long-form-writing.routing digest=d686d7a05c87568e227850189eba25cac48ab67adfa81999f1e34bf954090d9e -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:long-form-writing digest=f4af5eb1aa454b1f52e12b217390f26b9e03bb1e0b520fb5a7cc6e4e7e53ce12 -->
<!-- commands: agents/skills/catalog.yaml#skill:long-form-writing.tool_commands digest=5dff016c5ca24c413e9acd55ae62f87c036ab4a96d109e9d68524dd8e99f9802 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/long-form-writing.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# long-form-writing

## Canonical Skill

Canonical workflow and policy: [long-form-writing](../../../agents/skills/long-form-writing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill long-form-writing --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `5dff016c5ca24c413e9acd55ae62f87c036ab4a96d109e9d68524dd8e99f9802`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
