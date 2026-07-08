---
name: test-design
description: Use when a change needs oracle/spec-risk classification or resilient, adversarial static test design, including behavior contracts, oracle choice, property/metamorphic candidates, mutation adequacy, or brittle-test diagnosis.
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


1. Read `agents/skills/test-design.md`.
1. Record target code paths and related test paths as survey and placement evidence. Do not treat path evidence as authority to freeze API shape, private helper names, return shape, error prose, mock order or internal call sequence.
1. If related tests exist, run `tools/bin/agent-canon test-design check <related-test-paths...>` before reading whole files. Use `fix-now`, `review`, and `design-hint` findings as the first test-plan inputs.
1. Statically inspect branches, parsing, error handling, state transitions, observable behavior, and public contract boundaries.
1. Use this skill to classify oracle/spec risk and design tests when the changed behavior, regression risk, or unstable oracle needs it. Do not make test design a mandatory detour for every validation failure.
1. For algorithm fixes, enter through the algorithm contract and code-side
   repair route before changing tests. Read the public entrypoint, recurrence or
   state transition, invariant, stopping or acceptance rule, failure semantics,
   and selected repair route from the owning algorithm skill or design packet.
   Treat related tests as symptom, regression-placement, and oracle-risk
   evidence until that route is fixed.
1. Before adding or recommending a test, decide whether the property is already owned by static analysis, a checker, formatter, dependency review, type checker, lint, docs check, or CI gate. For checker-owned properties, route the canonical command as validation evidence.
1. Classify validation findings by validation repair scope before applying an autofix. Findings tied to the changed contract, changed lines, or checker-owned property named in the task plan enter the current repair; broad pre-existing style debt becomes residual evidence with a separate repair route.
1. When a test or check fails during validation, do not immediately simplify, revert, delete features or tests, lower oracle strength, or remove intended behavior to make it pass. First identify the failing contract and observation level.
1. Record the validation-failure-response fields `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`; use the slug sets and route semantics owned by `documents/runtime-profiles-and-check-matrix.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/canonical/CODEX_SUBAGENTS.md`, and `documents/REVIEW_PROCESS.md` for failure cause classification, approved intent preservation, and when to escalate before intent changes.
1. For `cause_classification=implementation_bug` with a stable contract, preserve approved intent and proceed to the owning code, config, docs, or workflow repair after classification; do not block that repair behind an extra test-design pass.
1. For algorithm bugs, update expected values, tolerances, and test oracle shape
   only after the algorithm contract and repair mechanism are fixed. Record
   why each test change follows the contract rather than the current failing
   output.
1. Before allowing behavior simplification, revert, intended-behavior removal, feature/test deletion, or oracle weakening, record a short failure-cause note in `test_plan.md`, work log, or review evidence.
1. For a `contract-only wrapper` or thin adapter, classify whether it adds observable behavior, branch logic, parser/error behavior, state mutation, diagnostic keys, serialization shape, or external process behavior. Names, types, forwards, configuration, and documentation for an existing contract use static contract validation and canonical command evidence.
1. Use API shape, helper identity, return shape, error prose, mock order or internal call sequence as test oracles only when the user request, approved design, documented external contract, or public behavior already fixes them. Otherwise record them under placement notes or `Do Not Freeze`.
1. For each test case, fix `Contract Source`, `Behavior Contract`, `Observation Level`, `Observable Outcome`, `Oracle`, `Input Space`, `Adequacy Evidence`, and `Do Not Freeze`.
1. Classify generated execution-only placeholders such as `test_runs`, `test_smoke`, `test_generated_*`, or `test_can_run` as checker-command validation candidates when they observe only process success, import success, no-crash, or exit code 0.
1. Route mathematical judgments, oracles, and assertions through the `mathematical necessity gate`: connect them to `Numerical Trigger`, `Non-Numerical Alternative`, checker-owned property, proof obligation, or approved design acceptance criterion before making them test evidence.
1. Before proposing numerical, randomized, tolerance, solver, convergence,
   residual, benchmark, or experiment-style tests, apply the Numerical Test Admission Gate from `documents/coding-conventions-testing.md`: record the
   numerical trigger, non-numerical alternative, oracle, GPU target, and budget.
   If the target behavior is not numerical, omit the numerical test and record
   the omission reason instead. Do not propose CPU computational tests as a
   fallback for numerical validation.
1. Prefer behavior examples for concrete regressions, property tests for broad input spaces, metamorphic tests when exact expected output is hard, and mutation testing when oracle strength is doubtful.
1. Record nasty edge cases and regression cases in `test_plan.md`.
1. Keep cases concrete at the stable observation level: contract source, input, observable outcome, oracle, `Do Not Freeze`, and why the case is nasty.
1. Mirror existing test style, fixture layout, and naming before suggesting anything new.
