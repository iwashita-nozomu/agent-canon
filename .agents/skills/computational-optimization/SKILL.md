---
name: computational-optimization
description: Use when designing, implementing, reviewing, or diagnosing numerical optimization, solvers, preconditioners, convergence, gradients, Jacobians, Hessians, KKT conditions, tolerances, or optimization benchmarks; fixes the mathematical and validation contract before code or experiment changes.
---
<!--
@dependency-start
responsibility Documents Computational Optimization for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/computational-optimization.md human-facing skill contract
upstream design ../../../agents/skills/research-workflow.md research outer-loop boundary
upstream design ../../../agents/skills/experiment-lifecycle.md experiment execution boundary
upstream design ../../../agents/skills/test-design.md adversarial test design boundary
@dependency-end
-->


# Computational Optimization

1. Read `agents/skills/computational-optimization.md`.
1. Use this skill for optimizer, solver, preconditioner, residual, KKT, convergence, derivative, tolerance, or numerical benchmark work.
1. Before implementation or experiment runs, fix an optimization contract: objective or residual, variables, constraints, derivatives, algorithm state, stopping policy, numerical invariants, and failure semantics.
1. For iterative solvers, treat convergence evidence as a theorem about the
   implemented iteration map and stopping scalar, e.g.
   `z_next = Step_impl(Problem, Config, z)` and
   `R_impl(Problem, Config, z)`. If this map cannot satisfy the target theorem
   under the accepted problem/config/backend assumptions, change the algorithmic
   mechanism itself. Do not add proof-only `Info` fields, diagnostic gates, or
   extra runtime checks merely to satisfy the proof.
1. For JAX/XLA/IREE iterative solvers, keep lowering-friendly loop structure in
   the implementation: do not feed residual / convergence / breakdown status
   produced inside `lax.while_loop` back into the next `cond`, and normalize
   Python scalar settings to dtype-specific JAX arrays at the JIT boundary. Use
   `documents/conventions/python/15_jax_rules.md` as the detailed code-writing
   rule.
1. If the task includes external method comparison or claims, also use `$research-workflow`; if it includes a concrete run protocol or rerun decision, also use `$experiment-lifecycle`.
1. If code changes are needed, use `$test-design` before implementation and include exact small cases, ill-conditioned cases, constraint-boundary cases, derivative checks, non-finite guards, and not-converged status handling when relevant.
1. Do not green numerical tests by relaxing tolerances, deleting assertions, skipping cases, changing expected values to match current output, or using CPU without an explicit reason.
1. Diagnose failed runs by first bad iteration, finite state before failure, residual components, reference norm, tolerance, status flag, and unconfirmed hypotheses; do not infer cause only from the final NaN, Inf, or residual.
1. Keep correctness evidence separate from performance evidence; benchmark claims need reproducibility and confounder review.
1. Route review by risk: `scientific_computing_reviewer` for math/numerical risk, `benchmark_reviewer` for performance claims, `$python-review` or `$cpp-review` for implementation diffs, and `$report-writing` for reader-facing claims.
