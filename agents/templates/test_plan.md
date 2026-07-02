# Test Plan
<!--
@dependency-start
contract template
responsibility Documents Test Plan for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Static Path Survey

<!-- Record code/test paths, branches, error handling, parsing logic, and state transitions as survey and placement evidence. Do not use path evidence to freeze unapproved API shape, private helpers, private return shape, error prose, mock order, or internal call sequence. -->

## Behavior Contract Matrix

| Contract Source | Behavior Contract | Observation Level | Observable Outcome | Oracle | Input Space | Adequacy Evidence | Do Not Freeze |
| --------------- | ----------------- | ----------------- | ------------------ | ------ | ----------- | ----------------- | ------------- |

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
