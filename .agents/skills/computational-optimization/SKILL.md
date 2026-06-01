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
1. If the task includes external method comparison or claims, also use `$research-workflow`; if it includes a concrete run protocol or rerun decision, also use `$experiment-lifecycle`.
1. If code changes are needed, use `$test-design` before implementation and include exact small cases, ill-conditioned cases, constraint-boundary cases, derivative checks, non-finite guards, and not-converged status handling when relevant.
1. Do not green numerical tests by relaxing tolerances, deleting assertions, skipping cases, changing expected values to match current output, or falling back to CPU without an explicit reason.
1. Diagnose failed runs by first bad iteration, finite state before failure, residual components, reference norm, tolerance, status flag, and unconfirmed hypotheses; do not infer cause only from the final NaN, Inf, or residual.
1. Keep correctness evidence separate from performance evidence; benchmark claims need reproducibility and confounder review.
1. Route review by risk: `scientific_computing_reviewer` for math/numerical risk, `benchmark_reviewer` for performance claims, `$python-review` or `$cpp-review` for implementation diffs, and `$report-writing` for reader-facing claims.
