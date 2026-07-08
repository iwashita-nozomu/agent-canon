---
name: computational-optimization
description: Use when designing, implementing, reviewing, or diagnosing numerical optimization, solvers, preconditioners, convergence, gradients, Jacobians, Hessians, KKT conditions, tolerances, or optimization benchmarks; fixes the mathematical and validation contract before code or experiment changes.
---
<!--
@dependency-start
contract skill
responsibility Documents Computational Optimization for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/computational-optimization.md human-facing skill contract
upstream design ../../../agents/skills/research-workflow.md research outer-loop boundary
upstream design ../../../agents/skills/experiment-lifecycle.md experiment execution boundary
upstream design ../../../agents/skills/test-design.md adversarial test design boundary
@dependency-end
-->


# Computational Optimization

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill computational-optimization --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/computational-optimization.md`.
1. Use this skill for optimizer, solver, preconditioner, residual, KKT, convergence, derivative, tolerance, or numerical benchmark work.
1. Before implementation or experiment runs, fix an optimization contract: objective or residual, variables, constraints, derivatives, algorithm state, stopping policy, numerical invariants, and failure semantics.
1. Route mathematical runtime checks, diagnostic gates, stopping checks, test
   oracles, and proof obligations through the `mathematical necessity gate`:
   connect each one to the public contract, iteration map, stopping scalar,
   failure semantics, accepted theorem target, or approved design acceptance
   criterion before adding it to implementation or validation evidence.
1. For iterative solvers, treat convergence evidence as a theorem about the
   implemented iteration map and stopping scalar, e.g.
   `z_next = Step_impl(Problem, Config, z)` and
   `R_impl(Problem, Config, z)`. If this map cannot satisfy the target theorem
   under the accepted problem/config/backend assumptions, change the algorithmic
   mechanism itself. Do not add proof-only `Info` fields, diagnostic gates, or
   extra runtime checks merely to satisfy the proof.
1. When tool-side routing returns `numerical_iterative_algorithm_contract`, build
   an explicit route packet before code changes: `iteration_map`,
   `stopping_scalar`, `state_tuple`, `reuse_surface`, `failure_semantics`, and
   `validation_surface`. Prefer existing solver/library/framework primitives or
   repo helpers as the first implementation surface, and keep correctness
   validation separate from experiment or benchmark evidence.
1. For algorithm fixes, enter through the optimization contract and implemented
   mechanism before changing tests. Record the public entrypoint, recurrence or
   state transition, invariant, stopping or acceptance scalar, and failure
   semantics; then select the code-side repair route. Existing tests are
   symptom and placement evidence, while expected values, tolerances, and new
   oracle cases are updated after the algorithm route is fixed.
1. Do not make the theorem pass by fixing the backend, device, compiler route,
   runtime target, or dtype unless the user request, approved design, runtime
   profile, public API, or config explicitly fixes that backend. Backend-specific
   data is evidence for the active profile, not a replacement for the
   optimization contract. Missing backend evidence is
   `backend_evidence_blocker`.
1. For JAX/XLA/IREE iterative solvers, keep lowering-friendly loop structure in
   the implementation: do not feed residual / convergence / breakdown status
   produced inside `lax.while_loop` back into the next `cond`, and normalize
   Python scalar settings to dtype-specific JAX arrays at the JIT boundary. Use
   `documents/conventions/python/15_jax_rules.md` as the detailed code-writing
   rule.
1. If the task includes external method comparison or claims, also use `$research-workflow`; if it includes a concrete run protocol or rerun decision, also use `$experiment-lifecycle`.
1. If code changes are needed, use `$test-design` after the optimization
   contract and algorithmic repair route are fixed, and include exact small
   cases, ill-conditioned cases, constraint-boundary cases, derivative checks,
   non-finite guards, and not-converged status handling when relevant.
1. Do not green numerical tests by relaxing tolerances, deleting assertions,
   skipping cases, changing expected values to match current output, or running
   computational tests on CPU; using CPU as substitute evidence is a validation
   blocker, not pass evidence. Solver, optimizer, JAX/XLA/IREE lowering,
   convergence, residual, benchmark, and experiment validation must run on the
   GPU target or be recorded as `gpu_validation_blocker=<reason>`.
1. Diagnose failed runs by first bad iteration, finite state before failure, residual components, reference norm, tolerance, status flag, and unconfirmed hypotheses; do not infer cause only from the final NaN, Inf, or residual.
1. Keep correctness evidence separate from performance evidence; benchmark claims need reproducibility and confounder review.
1. Route review by risk: `scientific_computing_reviewer` for math/numerical risk, `benchmark_reviewer` for performance claims, `$python-review` or `$cpp-review` for implementation diffs, and `$report-writing` for reader-facing claims.
