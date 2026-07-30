---
name: subagent-bootstrap
description: "Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:subagent-bootstrap -->
<!-- canonical: agents/skills/subagent-bootstrap.md sha256=58451a687a3a3a95bd9c2cc665696f7c42cba5680db8451d71ea5f946dc792a3 -->
<!-- route: agents/skills/catalog.yaml#skill:subagent-bootstrap.routing digest=b7334c5d5d2ba335df215efa0e1ea4c8d5b9a51c49b6b527c4fa130e85800598 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:subagent-bootstrap digest=9a95f230e3d7d60eaff77b610c4f63cf3f8a76da86c9ee1ef49b93e3a4a86037 -->
<!-- commands: agents/skills/catalog.yaml#skill:subagent-bootstrap.tool_commands digest=5d930bf9c93364e6ee3fb43400874db7e52c6f71888fbc65ec421caf65d33a52 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/subagent-bootstrap.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# subagent-bootstrap

## Canonical Skill

Canonical workflow and policy: [subagent-bootstrap](../../../agents/skills/subagent-bootstrap.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill subagent-bootstrap --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `5d930bf9c93364e6ee3fb43400874db7e52c6f71888fbc65ec421caf65d33a52`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
