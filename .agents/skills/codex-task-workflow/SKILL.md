---
name: codex-task-workflow
description: "Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:codex-task-workflow -->
<!-- canonical: agents/skills/codex-task-workflow.md sha256=6c87597b53a41f77ae1e55437f7e8dba8bab803fc38c726f7dbc54e2a044f01f -->
<!-- route: agents/skills/catalog.yaml#skill:codex-task-workflow.routing digest=b62ef8a5d9dc51d40389f5adf349b920943c2308ed63611356e325874293760b -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:codex-task-workflow digest=2af7374d7e96f1a1fad66ce67b13639c9d2be77e05a5860b6868d2139d327afb -->
<!-- commands: agents/skills/catalog.yaml#skill:codex-task-workflow.tool_commands digest=ee5089af5326e568668d92a75a1d0c2fa029b473595b9bada276842eca11865a -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/codex-task-workflow.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# codex-task-workflow

## Canonical Skill

Canonical workflow and policy: [codex-task-workflow](../../../agents/skills/codex-task-workflow.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill codex-task-workflow --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `ee5089af5326e568668d92a75a1d0c2fa029b473595b9bada276842eca11865a`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
