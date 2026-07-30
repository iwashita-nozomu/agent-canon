---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE backend execution, GPU validation blockers, nvidia-smi evidence, CUDA_VISIBLE_DEVICES handling, ExperimentRunner-based Python runs, or JAX/XLA preallocation-disabled execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"6786b0c30e6a55eeaad0fd9357805be47a09e6a5165404c0a55b8045f46ff7cd"} -->

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
