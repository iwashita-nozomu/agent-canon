<!--
@dependency-start
contract data
responsibility Records first-finite-breakpoint diagnosis knowledge for iterative numerical failures.
upstream design ../README.md memory record contract
upstream implementation ../../rust/agent-canon/src/memory.rs schema, validation, and search owner
upstream design ../../agents/skills/computational-optimization.md canonical numerical optimization owner
@dependency-end
-->

# First finite breakpoint diagnosis

record_id: `optimization--first-finite-breakpoint`
record_schema: `agent-canon.memory-record.v1`

## Problem/Symptom

数値処理の最終結果だけを見ると NaN、Inf、発散、または残差悪化に見える。

症状の名前を最終出力へ固定すると、最初に有限性・形状・境界条件を失った反復を見落とし、
原因ではなく downstream の副作用を修理してしまう。

## Context/Trigger

solver、反復最適化、gradient/Jacobian/Hessian、前処理を変更した後に、後段の
diagnostic が非有限値や異常残差を報告したときに使う。

## Root Cause

最終 failure は state transition の後段であり、最初の有限性 breakpoint、入力 state、
選択された branch、診断値を同時に保存しないと、最初の破綻を再現できない。反復ごとの
state と acceptance/stop condition の対応が欠けていることが根本原因になる。

## Effective Resolution

最初に有限性を失った iteration を特定し、その直前の finite state、入力、branch、
diagnostic、invariant、stop/acceptance 条件を記録する。最後の NaN/Inf や residual ではなく、
最初の breakpoint の recurrence を owner の algorithm contract と実装へ戻して修理する。

## Failed Approaches

- 最終出力だけを assertion の対象にして原因を後付けする。
- tolerance を緩めて非有限値を通す。
- production state transition を確認せず test-only wrapper で症状を隠す。

## Applicability/Limits

反復・状態遷移を持つ数値処理に適用する。純粋な入力形式エラーや、有限性を持たない
離散処理の failure の一般診断法ではない。収束判定や許容値の変更は owner contract の
選択を伴うため、この record だけで決めない。

## Evidence/Source

AgentCanon main base `161a61d72ad5b05d3646010819b4fa5f37725427` 上の数値診断の作業哲学と、
computational optimization skill の finite-state / first-breakpoint guidance を評価した結果。

## Promoted Owner Refs

- `agents/skills/computational-optimization.md`

## Related Records

- なし
