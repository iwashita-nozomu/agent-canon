---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE execution, selecting an available GPU index or UUID for native Docker, optional free-GPU admission or reservation, nvidia-smi evidence, arbitrary pytest/benchmark/diagnostic argv, managed ExperimentRunner runs, GPU validation blockers, or preallocation-disabled JAX/XLA execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"7442c2c8e9f0a7a7fb5d097717b0c05ca28579b242e313981bde53514c2d5903"} -->

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

1. Read the canonical owner before applying this skill.
