---
name: gpu-execution
description: Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE backend execution, GPU validation blockers, nvidia-smi evidence, CUDA_VISIBLE_DEVICES handling, ExperimentRunner-based Python runs, or JAX/XLA preallocation-disabled execution.
---
<!--
@dependency-start
contract skill
responsibility Documents GPU Execution for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/gpu-execution.md human-facing GPU execution contract
upstream design ../../../documents/experiment_runner.md ExperimentRunner responsibility boundary
upstream design ../../../documents/conventions/python/15_jax_rules.md JAX GPU preallocation and CPU fallback policy
upstream design ../../../agents/workflows/experiment-workflow.md managed experiment execution workflow
@dependency-end
-->

# GPU Execution

## Reader Map

- Purpose: runtime skill for GPU/CUDA/JAX/XLA/IREE execution routing,
  ExperimentRunner delegation, preallocation-disabled JAX runs, and GPU blocker
  evidence.
- Use When: a task asks to run or validate on GPU, diagnose CUDA/JAX/XLA backend
  behavior, handle `CUDA_VISIBLE_DEVICES`, collect `nvidia-smi` evidence, or
  disable JAX/XLA preallocation.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/gpu-execution.md` contract and task-matching owner docs.
- Boundary: this skill owns GPU runtime evidence; experiment protocol,
  numerical correctness, and code review stay with their owner skills.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill gpu-execution --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/gpu-execution.md`.
1. Pair this skill with `$experiment-lifecycle` when the GPU run is an
   experiment, benchmark, smoke run, formal run, or rerun decision.
1. Pair this skill with `$computational-optimization` when solver, optimizer,
   residual, convergence, tolerance, or numerical benchmark correctness is in
   scope.
1. Before scheduling a GPU / CPU numerical run, create or cite the task-linked
   execution note required by `$agent-orchestration`: request clause, command
   type, lightweight evidence, expected runtime, resource target, stop
   condition, artifact path, and owner.
1. For Python GPU execution, use ExperimentRunner or the managed experiment
   wrapper as the formal execution route. The experiment side supplies `task`,
   `cases`, `context_builder`, `initializer`, `resource_estimate`, and optional
   `SkipController`; `experiment_runner` owns process lifecycle, timeout,
   cleanup, diagnostics, `ExecutionResult`, worker slots, GPU slots, and child
   environment reflection.
1. Pass device and allocator environment through
   `TaskContext["environment_variables"]` and the child initializer. Do not
   assemble `CUDA_VISIBLE_DEVICES`, `NVIDIA_VISIBLE_DEVICES`, or `XLA_*` inside
   the experiment task body or case loop.
1. For JAX / XLA GPU execution, set `XLA_PYTHON_CLIENT_PREALLOCATE=false` before
   JAX import. When the project helper supports the allocator knobs, also carry
   `XLA_PYTHON_CLIENT_ALLOCATOR=platform` and
   `XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false`.
1. If CUDA backend initialization or GPU allocation is unavailable, record
   `gpu_validation_blocker=<reason>` with `nvidia-smi`, scheduler, or runner
   evidence. Do not replace a GPU validation or backend claim with CPU
   computation.
1. Close out with `gpu_execution_route=experiment_runner`,
   `preallocation_disabled=yes`, run artifact paths, GPU slot metadata, and
   `gpu_validation_blocker=none` or the recorded blocker.
