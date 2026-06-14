---
name: test-design
description: Use when code changes need resilient, adversarial static test design before implementation, including behavior contracts, oracle choice, property/metamorphic candidates, mutation adequacy, or brittle-test diagnosis.
---
<!--
@dependency-start
responsibility Documents Test Design for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Test Design

1. Read `agents/skills/test-design.md`.
1. Fix the target code paths and related test paths.
1. If related tests exist, run `tools/bin/agent-canon test-design check <related-test-paths...>` before reading whole files. Use `fix-now`, `review`, and `design-hint` findings as the first test-plan inputs.
1. Statically inspect branches, parsing, error handling, state transitions, observable behavior, and public contract boundaries.
1. For each test case, fix `Behavior Contract`, `Observation Level`, `Oracle`, `Input Space`, and `Adequacy Evidence`.
1. Before proposing numerical, randomized, tolerance, solver, convergence, residual, benchmark, or experiment-style tests, apply the Numerical Test Admission Gate from `documents/coding-conventions-testing.md`: record the numerical trigger, non-numerical alternative, oracle, and budget. If the target behavior is not numerical, omit the numerical test and record the omission reason instead.
1. Prefer behavior examples for concrete regressions, property tests for broad input spaces, metamorphic tests when exact expected output is hard, and mutation testing when oracle strength is doubtful.
1. Record nasty edge cases and regression cases in `test_plan.md`.
1. Keep cases concrete: target, input, expected outcome, oracle, and why the case is nasty.
1. Mirror existing test style, fixture layout, and naming before suggesting anything new.
