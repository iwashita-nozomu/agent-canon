---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE execution, free-GPU admission, full UUID or MIG selection, nvidia-smi evidence, arbitrary pytest/benchmark/diagnostic argv, managed ExperimentRunner runs, GPU validation blockers, or preallocation-disabled JAX/XLA execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"425e6256532c658cb4a10eb9cae59611bb20df75171b9ce7ca261b0e40be1b20"} -->

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
