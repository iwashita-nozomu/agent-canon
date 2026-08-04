# Real protocol fixture reuse

record_id: `testing--real-protocol-fixture-reuse`
record_schema: `agent-canon.memory-record.v1`

## Problem/Symptom

新しい interface の test で、実装を通すためだけの production wrapper、subclass、または
test-only protocol object を増やすと、test は通っても実 repository surface との境界がずれる。

## Context/Trigger

既存の repository surface が実 protocol を実装しているのに、unit test の都合で最小 fake を
production code に追加したくなったときに使う。

## Root Cause

unit と integration の責務を分けず、fixture の最小性を production abstraction の追加で
解決している。production 側の責務境界と実 protocol の利用箇所を確認していないため、
test double が canonical surface の代替になってしまう。

## Effective Resolution

unit test では必要な protocol を満たす最小 fixture を test scope に閉じ込め、integration test
では実 repository surface と real protocol fixture を再利用する。production wrapper を追加する
前に owner、import boundary、既存 fixture の再利用可否を確認し、追加が必要なら設計境界を
先に更新する。

## Failed Approaches

- test のためだけに production subclass や adapter を追加する。
- real surface を使わず、fake の通過だけで integration compatibility を主張する。
- fixture の不足を test oracle の変更で隠す。

## Applicability/Limits

protocol/interface boundary と unit/integration の使い分けに適用する。外部 system が
不可避で、契約済みの test double が owner によって定義されている場合は、その fixture owner
を優先する。実 surface の再利用は test isolation を無条件に犠牲にする意味ではない。

## Evidence/Source

main base の test routing 知識を、test design の admission boundary と production/test scope
分離の owner と照合して記録した。#536 open draft 固有の memory は含めていない。

## Promoted Owner Refs

- `agents/skills/test-design.md`

## Related Records

- なし
