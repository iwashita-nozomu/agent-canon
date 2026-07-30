---
name: agent-orchestration
description: "Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-orchestration -->
<!-- canonical: agents/skills/agent-orchestration.md sha256=cebe3b719aa1a04e4110e1f07893def08a46cddfe1d8bfa49b7251eb9878a5b6 -->
<!-- route: agents/skills/catalog.yaml#skill:agent-orchestration.routing digest=3f8c23709a63eb8c7af65da6ba22becbfb9edb77c7320080d8b955bcf1c49b89 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-orchestration digest=cb5ffbaa6b1fff3996a1c6e7c8320778a62a50162a4e53f4db6db1c855462075 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-orchestration.tool_commands digest=adb5f208c3beab6a61a81da68764e04acf22840014be6a878c4411e61a606641 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/agent-orchestration.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# agent-orchestration

## Canonical Skill

Canonical workflow and policy: [agent-orchestration](../../../agents/skills/agent-orchestration.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `adb5f208c3beab6a61a81da68764e04acf22840014be6a878c4411e61a606641`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
