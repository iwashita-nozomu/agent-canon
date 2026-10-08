---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE execution, selecting an available GPU index or UUID for native Docker, optional free-GPU admission or reservation, nvidia-smi evidence, arbitrary pytest/benchmark/diagnostic argv, managed ExperimentRunner runs, GPU validation blockers, or preallocation-disabled JAX/XLA execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"8020d4e5735a9f7d452bfb4da001540248c885fd8cdb9f1928f72233c3c79dde"} -->

<!--
@dependency-start
contract skill
responsibility Exposes gpu-execution for runtime discovery.
upstream design ../../../../agents/skills/gpu-execution.md owner
@dependency-end
-->

# gpu-execution

## Canonical Skill

Canonical workflow and policy: [gpu-execution](../../../../agents/skills/gpu-execution.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill gpu-execution --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
