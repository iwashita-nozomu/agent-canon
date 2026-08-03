# Test Plan（test 計画）
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

## Static Path Survey（static path 調査）

<!-- code/test path、branch、error handling、parsing logic、state transition を survey と placement evidence として記録します。path evidence で未承認の API shape、private helper、private return shape、error prose、mock order、internal call sequence を固定しません。 -->

## Behavior Contract Matrix（behavior contract matrix）

| Contract Source | Behavior Contract | Observation Level | Observable Outcome | Oracle | Input Space | Adequacy Evidence | Do Not Freeze |
| --------------- | ----------------- | ----------------- | ------------------ | ------ | ----------- | ----------------- | ------------- |

## Algorithm Contract Before Tests（tests より前の algorithm contract）

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

## Necessary-And-Sufficient Oracle Boundary（必要十分 oracle 境界）

- necessary observations:
- sufficient observations:
- oracle owner:
- not proven by this oracle:
- test activation condition:
- static/targeted route when test is not necessary:

## Failure Cause And Conflict Intent（failure cause と conflict intent）

- failure-cause class: expected / infrastructure / implementation / oracle / unknown:
- evidence and owner:
- conflict intent / preserved design or user clause:
- escalation or rejection evidence:

## Contract-Only Wrapper Classification（contract-only wrapper の分類）

| Wrapper / Adapter | Observable Trigger | Static Validation Route | Classification | Notes |
| ----------------- | ------------------ | ----------------------- | -------------- | ----- |

<!-- observable behavior、branch、parser/error behavior、public state mutation、diagnostic key、serialization shape、external process behavior がなければ、execution-only test を追加せず static contract validation と canonical command evidence に戻します。 -->

## Nasty Cases（難しい case）

| Contract Source | Observation Level | Case | Why It Is Nasty | Observable Outcome | Oracle | Status |
| --------------- | ----------------- | ---- | --------------- | ------------------ | ------ | ------ |

## Regression Cases To Keep（保持する regression case）

<!-- 以前壊れた、または再発しやすく durable test にすべき scenario を記録します。 -->

## Placement Notes（配置メモ）

<!-- test の配置先、mirror する既存 style/fixture/naming pattern、survey evidence だけに使った path を記録します。 -->

## Implementation Notes（implementation メモ）

<!-- validation route を記録します。behavior-owned case では新しい public API、helper、return-shape、error-prose、mock-order、internal-call-sequence contract を導入せず placement note を指します。 -->
