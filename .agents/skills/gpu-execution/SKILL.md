---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE backend execution, GPU validation blockers, nvidia-smi evidence, CUDA_VISIBLE_DEVICES handling, ExperimentRunner-based Python runs, or JAX/XLA preallocation-disabled execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"5f1f3e0b53c26492453987eab888b09f4b506f060ede8f246979fe64e0b58537"} -->

<!--
@dependency-start
contract skill
responsibility Exposes gpu-execution for runtime discovery.
upstream design ../../../agents/skills/gpu-execution.md owner
@dependency-end
-->

# gpu-execution

## Canonical Skill

Canonical workflow and policy: [gpu-execution](../../../agents/skills/gpu-execution.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill gpu-execution --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
