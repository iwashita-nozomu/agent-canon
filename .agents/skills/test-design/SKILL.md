---
name: test-design
description: Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases.
---
<!--
@dependency-start
contract skill
responsibility Documents Test Design for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Test Design

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill test-design --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/test-design.md` and return `Activation Decision` first. This is
   a post-start classification, not a pre-start gate; once selected, run the
   classification before deciding the test cases.
1. Confirm that the owning production design / algorithm contract and implementation mechanism are established or repaired. If not, return `activation=deferred` with the owning repair route; do not run tools or require `test_plan.md`.
1. Confirm a concrete unresolved oracle, specification, regression, or failure-mode risk remains outside static analysis, existing checkers, and targeted validation. Ordinary code changes, bug fixes, parser changes, and validation failures alone do not justify unlimited test creation.
1. If the risk is absent or checker-owned, return `activation=not_needed` with the canonical validation route; do not run test-design tools or require `test_plan.md`.
1. Only for `activation=required`, record code paths and related test paths as survey and placement evidence, inspect branches/parsing/error/state transitions, and design a concrete behavior-regression oracle.
1. `activation=required` does not mean exhaustive test generation. Choose one
   stable observation level per unresolved risk, reuse one case when it covers
   multiple risks, and omit duplicate contract checks, no-crash checks, and
   internal-shape checks already owned by static validation or existing tests.
1. Only for `activation=required`, read both the owning design / contract document and the code-side implementation mechanism. Record the design clause, public entrypoint, branches, parsing and error paths, state transitions, and return projection that implement the claim; do not infer the contract from tests alone.
1. For every nasty or regression case under `activation=required`, require one complete trace: `Design Clause -> Code Mechanism -> Breaking Input/Sequence -> Observation Level / Observable Outcome -> Oracle`. A case is not evidence until the design clause, mechanism, concrete breaking input or state sequence, stable observation, and decidable oracle are all explicit.
1. During the mechanism survey, actively search for implementation assumptions that the contract does not guarantee. Include cases where inputs have the same element count but different shape, axis, or layout, as well as ordering or aliasing differences, empty or singleton values, boundary values, history-dependent state sequences, and retry-after-failure paths. Record the assumption challenged, the concrete input or sequence, and the observable divergence.
1. Before implementation or handoff, state a non-occurrence claim / null hypothesis for every candidate case: why the contract, type constraints, or an existing checker allegedly makes the case impossible.
1. Search for a reachability witness from the public input surface or a public state sequence. If no witness exists, do not turn the candidate into a test; return it to the checker, static-validation, or owning-design boundary. If a witness exists, record the evidence that refutes the null hypothesis and the observable oracle, and allow implementation or handoff only after this gate passes.
1. For algorithm fixes, enter through the algorithm contract and code-side
   repair route before changing tests. Read the public entrypoint, recurrence or
   state transition, invariant, stopping or acceptance rule, failure semantics,
   and selected repair route from the owning algorithm skill or design packet.
   Treat related tests as symptom, regression-placement, and oracle-risk
   evidence until that route is fixed.
1. Before adding or recommending a test, decide whether the property is already owned by static analysis, a checker, formatter, dependency review, type checker, lint, docs check, or CI gate. For checker-owned properties, route the canonical command as validation evidence.
1. Classify validation findings by validation repair scope before applying an autofix. Findings tied to the changed contract, changed lines, or checker-owned property named in the task plan enter the current repair; broad pre-existing style debt becomes residual evidence with a separate repair route.
1. When a test or check fails during validation, do not immediately simplify, revert, delete features or tests, lower oracle strength, or remove intended behavior to make it pass. First identify the failing contract and observation level.
1. Record the validation-failure-response fields `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`; use the slug sets and route semantics owned by `documents/runtime/runtime-profiles-and-check-matrix.json` for failure cause classification, approved intent preservation, and when to escalate before intent changes. Treat `documents/runtime/runtime-profiles-and-check-matrix.md` as the generated reader projection.
1. For `cause_classification=implementation_bug` with a stable contract, preserve approved intent and proceed to the owning code, config, docs, or workflow repair after classification; do not block that repair behind an extra test-design pass.
1. For algorithm bugs, update expected values, tolerances, and test oracle shape
   only after the algorithm contract and repair mechanism are fixed. Record
   why each test change follows the contract rather than the current failing
   output.
1. Before allowing behavior simplification, revert, intended-behavior removal, feature/test deletion, or oracle weakening, record a short failure-cause note in `test_plan.md`, work log, or review evidence.
1. For a `contract-only wrapper` or thin adapter, classify whether it adds observable behavior, branch logic, parser/error behavior, state mutation, diagnostic keys, serialization shape, or external process behavior. Names, types, forwards, configuration, and documentation for an existing contract use static contract validation and canonical command evidence.
1. Use API shape, helper identity, return shape, error prose, mock order or internal call sequence as test oracles only when the user request, approved design, documented external contract, or public behavior already fixes them. Otherwise record them under placement notes or `Do Not Freeze`.
1. For each required test case, fix `Contract Source`, `Behavior Contract`, `Observation Level`, `Observable Outcome`, `Oracle`, `Input Space`, `Adequacy Evidence`, and `Do Not Freeze`.
1. Classify generated execution-only placeholders such as `test_runs`, `test_smoke`, `test_generated_*`, or `test_can_run` as checker-command validation candidates when they observe only process success, import success, no-crash, or exit code 0.
1. Route mathematical judgments, oracles, and assertions through the `mathematical necessity gate`: connect them to `Numerical Trigger`, `Non-Numerical Alternative`, checker-owned property, proof obligation, or approved design acceptance criterion before making them test evidence.
1. Before proposing numerical, randomized, tolerance, solver, convergence,
   residual, benchmark, or experiment-style tests, apply the Numerical Test Admission Gate from `documents/conventions/coding-conventions-testing.md`: record the
   numerical trigger, non-numerical alternative, oracle, GPU target, and budget.
   If the target behavior is not numerical, omit the numerical test and record
   the omission reason instead. Do not propose CPU computational tests as a
   fallback for numerical validation.
1. Prefer behavior examples for concrete regressions, property tests for broad input spaces, metamorphic tests when exact expected output is hard, and mutation testing when oracle strength is doubtful.
1. Record nasty edge cases and regression cases in `test_plan.md` only when `activation=required`.
1. Keep cases concrete at the stable observation level: `Design Clause`, `Code Mechanism`, `Breaking Input/Sequence`, `Observation Level`, `Observable Outcome`, `Oracle`, `Input Space`, `Adequacy Evidence`, `Do Not Freeze`, and why the case is nasty. Do not add tests merely to increase test count or coverage without this trace.
1. Mirror existing test style, fixture layout, and naming before suggesting anything new.
