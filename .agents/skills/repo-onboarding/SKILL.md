---
name: repo-onboarding
description: "Use when entering an unfamiliar repository or subdirectory and you need the fastest safe path to the repo overview, commands, conventions, and agent canon."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:repo-onboarding -->
<!-- canonical: agents/skills/repo-onboarding.md sha256=75d59ce92962442d084dc0ce637837815b2948d14c814150f5835c91792c0486 -->
<!-- route: agents/skills/catalog.yaml#skill:repo-onboarding.routing digest=1d6e0fde0de0427d4bec430a8a7fd41fcd31f1456b967ba68a4e374f018e44f5 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:repo-onboarding digest=d367ae94b3aff8b85cf348905dcd3c2e012dbbd0c14da2b7e3ce0774a32607f9 -->
<!-- commands: agents/skills/catalog.yaml#skill:repo-onboarding.tool_commands digest=0ef9d5a5b66314227cc1193c58087a60454608cbf746029720c959809247ecca -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/repo-onboarding.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# repo-onboarding

## Canonical Skill

Canonical workflow and policy: [repo-onboarding](../../../agents/skills/repo-onboarding.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill repo-onboarding --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `0ef9d5a5b66314227cc1193c58087a60454608cbf746029720c959809247ecca`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
