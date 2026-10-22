---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE execution, selecting an available GPU index or UUID for native Docker, optional free-GPU admission or reservation, nvidia-smi evidence, arbitrary pytest/benchmark/diagnostic argv, managed ExperimentRunner runs, GPU validation blockers, or preallocation-disabled JAX/XLA execution."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"1d16947932cd93d4e8444ca87df35ba6a79ea3ba7bb101a4a77889c64ccc3865"} -->

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
