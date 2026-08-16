# Tests And Oracles Audit Unit
<!--
@dependency-start
contract design
responsibility Audits necessary and sufficient tests, regression oracles, and native validation selection.
upstream design ../README.md owns static-first and validation boundaries
upstream design ../../runtime/runtime-profiles-and-check-matrix.md owns profile-specific validation
upstream implementation ../../../agents/skills/test-design.md owns unresolved oracle design
downstream implementation ../../../agents/skills/python-review.md and ../../../agents/skills/cpp-review.md own native test repair
@dependency-end
-->

## Reader Map

変更された production mechanism、invariant、既存 test oracle、必要な regression の順に
読みます。static evidence で十分なら runtime test を増やさず、未解決の oracle がある
場合だけ `test-design` へ routing します。

## Owner Responsibility

`test-design` は unresolved oracle、specification、regression、failure-mode の設計を
所有します。実装言語の owner skill が test の修正と native execution を所有します。

## Invariant

必要な test は production contract と対象 failure mode を検証し、十分性を超える全 suite、
未関係の fixture、test-only production branch、oracle の無根拠な緩和を追加しない。

## Evidence Sources

- production design、invariant、acceptance rule
- 既存 `tests/` と project-native test command
- profile check matrix
- `pytest`、native configure/build/test、必要な static checker の結果
- test-designer の oracle packet（未解決時のみ）

## Repair Route

owner skill は `test-design`、実装 owner は `python-review` または `cpp-review`。先に
production mechanism を固定し、必要な test だけを writer に委譲します。static で完結する
項目は test を作らず readback で close します。

## Validation

変更言語と対象 contract に対応する targeted test、必要な既存 regression、native toolchain
の最小 command を選びます。全 `tests/`、全 CI、Docker image diff build は unit が明示的に
必要としない限り実行しません。

## Close Condition

test oracle が invariant に対応し、対象 test が pass し、不要な追加 test/check がなく、
test output と変更 source の readback が一致する。実行不能なら `repair_blocked` と理由を
記録して次 unit へ進む。

## Related Change Surfaces

`surface:tests.oracle`、`surface:runtime.validation`、`surface:code.behavior`。production
contract、test oracle、validation matrix、test routing の変更時だけ本 unit を更新します。

## Legacy Migration IDs

PRA-C050 PRA-C051 PRA-X034
