---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE backend execution, GPU validation blockers, nvidia-smi evidence, CUDA_VISIBLE_DEVICES handling, ExperimentRunner-based Python runs, or JAX/XLA preallocation-disabled execution."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:gpu-execution -->
<!-- canonical: agents/skills/gpu-execution.md sha256=11baaaa3c5011c6b9b9c23d75a4eb5891783d65a22ad05ef5fa87323d91474d9 -->
<!-- route: agents/skills/catalog.yaml#skill:gpu-execution.routing digest=33bafddb4378acdb9dcff135ab024c394854ce3398acf0990060e939be3f9502 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:gpu-execution digest=bd0ae3050ce484b65e9e4216a2da77b22f0387f8ba34965204c4f861d1fd3030 -->
<!-- commands: agents/skills/catalog.yaml#skill:gpu-execution.tool_commands digest=5f8e33ef7f2752e7f76351e083bb0e21e2dfcf0d89c76fdd49e4959688985536 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/gpu-execution.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# gpu-execution

## Canonical Skill

Canonical workflow and policy: [gpu-execution](../../../agents/skills/gpu-execution.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill gpu-execution --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `5f8e33ef7f2752e7f76351e083bb0e21e2dfcf0d89c76fdd49e4959688985536`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
