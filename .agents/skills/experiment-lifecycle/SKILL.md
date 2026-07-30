---
name: experiment-lifecycle
description: "Use this skill when preparing, running, or validating experiments."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:experiment-lifecycle -->
<!-- canonical: agents/skills/experiment-lifecycle.md sha256=3d8b0f4705d6499cd86b29c69bbd7179218ee8f7efbedbfa36a9b34c757ecf81 -->
<!-- route: agents/skills/catalog.yaml#skill:experiment-lifecycle.routing digest=920be5167b67012e02c6f64d6b571627479c25d3d63508cb6d088156e8427f00 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:experiment-lifecycle digest=03b4becafba4dd8a413e7c1848787007db27190f8fa70d49033f96eaeab08c94 -->
<!-- commands: agents/skills/catalog.yaml#skill:experiment-lifecycle.tool_commands digest=78d5fe86b6f2e41b342e9b1ff747712814d7efac6892e7b989261e4b239b5a9a -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/experiment-lifecycle.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# experiment-lifecycle

## Canonical Skill

Canonical workflow and policy: [experiment-lifecycle](../../../agents/skills/experiment-lifecycle.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-lifecycle --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `78d5fe86b6f2e41b342e9b1ff747712814d7efac6892e7b989261e4b239b5a9a`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
