---
name: experiment-review
description: "Use when reviewing experiment topics, run.py files, experiment registries, GPU/JAX environment ownership, notebook artifacts, or experiment README/report readiness."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:experiment-review -->
<!-- canonical: agents/skills/experiment-review.md sha256=a41e786c382f4812405f3cb0b44c29409c2e2c5537c38eaa89a70c4e6e77fce9 -->
<!-- route: agents/skills/catalog.yaml#skill:experiment-review.routing digest=ca0233b63511f7e15972d7f9218b5ed8e01932eb7e97f4622d8549098a0b5172 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:experiment-review digest=19776c6bad7af02179a02b6b4b8d993bc2a41e9a7025b60117b14b105b07610e -->
<!-- commands: agents/skills/catalog.yaml#skill:experiment-review.tool_commands digest=e861f8eb537d69d14988a3239f2e8e8db82b20e3f135c08fea7c210e05dd98c4 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/experiment-review.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# experiment-review

## Canonical Skill

Canonical workflow and policy: [experiment-review](../../../agents/skills/experiment-review.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-review --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `e861f8eb537d69d14988a3239f2e8e8db82b20e3f135c08fea7c210e05dd98c4`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
