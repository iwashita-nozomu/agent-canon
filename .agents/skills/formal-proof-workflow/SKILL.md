---
name: formal-proof-workflow
description: "Use when natural-language mathematical claims, JIT-canonical implementation claims, proof sketches, or theory assumptions should be converted into formal-proof obligations, generated Lean evidence, theorem-graph targets, and checker-gated evidence."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:formal-proof-workflow -->
<!-- canonical: agents/skills/formal-proof-workflow.md sha256=ca8d1ec533692ec2a37cc4cc7e2696ab686478fd3f1b7f6bb0dd102f2b17cef4 -->
<!-- route: agents/skills/catalog.yaml#skill:formal-proof-workflow.routing digest=a79339fed19116d6d9d68bb12ff0a4a905cba780e759bdcfc17f4a1f78f6a827 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:formal-proof-workflow digest=2ee4adcb4c8025c50fc9b214281d46ea65a7e51a64a738941496a1f04f1f688d -->
<!-- commands: agents/skills/catalog.yaml#skill:formal-proof-workflow.tool_commands digest=d083cd7b7b198d09e120a31dd72cb6b63217e4aabdc1427e98f608594ac27913 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/formal-proof-workflow.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# formal-proof-workflow

## Canonical Skill

Canonical workflow and policy: [formal-proof-workflow](../../../agents/skills/formal-proof-workflow.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill formal-proof-workflow --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `d083cd7b7b198d09e120a31dd72cb6b63217e4aabdc1427e98f608594ac27913`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
