---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:worktree-health -->
<!-- canonical: agents/skills/worktree-health.md sha256=def33b3721eae5d0ddb6ac957b240f4265f6bf9c2624a8923a2d938044583d92 -->
<!-- route: agents/skills/catalog.yaml#skill:worktree-health.routing digest=41008a69c6a7d7b76c1fd6936f8d71b5679989941c22c539fea30650d599c618 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:worktree-health digest=b67e161607cfc64bcf70b226f7f0c3b565b202e85549ed98891d6b3eeb37953a -->
<!-- commands: agents/skills/catalog.yaml#skill:worktree-health.tool_commands digest=70024e38cd3e1a7d5d4f4a7fa9bcb49017a9213d5772286edd39e050743696c8 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/worktree-health.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# worktree-health

## Canonical Skill

Canonical workflow and policy: [worktree-health](../../../agents/skills/worktree-health.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-health --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `70024e38cd3e1a7d5d4f4a7fa9bcb49017a9213d5772286edd39e050743696c8`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
