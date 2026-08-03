# Test Plan
<!--
@dependency-start
contract template
responsibility Documents Test Plan for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

## Static Path Survey

<!-- Record code/test paths, branches, error handling, parsing logic, and state transitions as survey and placement evidence. Do not use path evidence to freeze unapproved API shape, private helpers, private return shape, error prose, mock order, or internal call sequence. -->

## Behavior Contract Matrix

| Contract Source | Behavior Contract | Observation Level | Observable Outcome | Oracle | Input Space | Adequacy Evidence | Do Not Freeze |
| --------------- | ----------------- | ----------------- | ------------------ | ------ | ----------- | ----------------- | ------------- |

## Algorithm Contract Before Tests

テストの expected value や private call sequence を先に固定せず、production design の
public entrypoint、input domain、state transition/recurrence、invariant、stopping/acceptance、
typed failure を記録します。

- algorithm contract source:
- public behavior / observable state:
- state transition or recurrence:
- invariants and preconditions:
- stopping / acceptance rule:
- failure semantics and preserved artifacts:
- implementation mechanism:

## Necessary-And-Sufficient Oracle Boundary

- necessary observations:
- sufficient observations:
- oracle owner:
- not proven by this oracle:
- test activation condition:
- static/targeted route when test is not necessary:

## Failure Cause And Conflict Intent

- failure-cause class: expected / infrastructure / implementation / oracle / unknown:
- evidence and owner:
- conflict intent / preserved design or user clause:
- escalation or rejection evidence:

## Contract-Only Wrapper Classification

| Wrapper / Adapter | Observable Trigger | Static Validation Route | Classification | Notes |
| ----------------- | ------------------ | ----------------------- | -------------- | ----- |

<!-- If there is no observable behavior, branch, parser/error behavior, public state mutation, diagnostic key, serialization shape, or external process behavior, route validation back to static contract validation and canonical command evidence instead of adding execution-only tests. -->

## Nasty Cases

| Contract Source | Observation Level | Case | Why It Is Nasty | Observable Outcome | Oracle | Status |
| --------------- | ----------------- | ---- | --------------- | ------------------ | ------ | ------ |

## Regression Cases To Keep

<!-- Record previously broken or easy-to-rebreak scenarios that must become durable tests. -->

## Placement Notes

<!-- Record where tests should live, which existing style/fixture/naming pattern to mirror, and which paths were used only as survey evidence. -->

## Implementation Notes

<!-- Record the validation route. For behavior-owned cases, point to placement notes instead of introducing new public API, helper, return-shape, error-prose, mock-order, or internal-call-sequence contracts. -->
