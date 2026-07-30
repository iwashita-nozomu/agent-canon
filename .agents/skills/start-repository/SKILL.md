---
name: start-repository
description: "Use when starting a new GitHub/submodule-first repository from this template after clone, including project slug/display-name setup and AgentCanon submodule validation."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:start-repository -->
<!-- canonical: agents/skills/start-repository.md sha256=b0ea7179a6b1c709868c1c1e2ac6f0462fd9b8d1b3da6b774450a235fb934915 -->
<!-- route: agents/skills/catalog.yaml#skill:start-repository.routing digest=833ea3b9cdd7836cde78621fbd8e242bcf8ebd3e01f76cbdcaea1baa3ad68712 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:start-repository digest=83944f0fc56d48f7819caf0fab6d949c12575b4baafefa707a5f2f0268f9eaf7 -->
<!-- commands: agents/skills/catalog.yaml#skill:start-repository.tool_commands digest=33ea72446f4d0e3e98eb2610226e78cc1cac985acbc9d69ba3e8d00f6d80bd34 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/start-repository.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# start-repository

## Canonical Skill

Canonical workflow and policy: [start-repository](../../../agents/skills/start-repository.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill start-repository --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `33ea72446f4d0e3e98eb2610226e78cc1cac985acbc9d69ba3e8d00f6d80bd34`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
