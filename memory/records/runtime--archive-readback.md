<!--
@dependency-start
contract data
responsibility Records remote archive readback knowledge for publication closeout.
upstream design ../README.md memory record contract
upstream implementation ../../rust/agent-canon/src/memory.rs schema, validation, and search owner
upstream design ../../documents/runtime/runtime-log-archive.md canonical runtime archive owner
@dependency-end
-->

# Runtime archive readback

record_id: `runtime--archive-readback`
record_schema: `agent-canon.memory-record.v1`

## Problem/Symptom

archive publish や push が成功しても、remote に期待した branch、commit、tree、artifact が
存在するとは限らない。local success だけを closeout evidence にすると、後で archive の
readback が不足していることが分かる。

## Context/Trigger

runtime log、eval report、run bundle、または AgentCanon branch を archive/repository へ
publish した後、closeout や次の agent がその成果物を読むときに使う。

## Root Cause

publication の exit status と remote identity/readback を同じ completion evidence とみなして
いる。source、branch、commit/tree、remote object、取得可能性を named identity で照合していない。

## Effective Resolution

publish 前に対象 repository、branch、commit/tree、artifact path を named identity として
固定し、publish 後に remote ls/readback と必要な archive checkout を行う。local status、remote
identity、読めた artifact の三つを closeout evidence に束ね、readback 失敗は成功扱いにしない。

## Failed Approaches

- push の exit code だけで archive 完了と判断する。
- local clone の HEAD だけを remote readback の代わりにする。
- archive の raw chronology を memory record に append して証拠の正本にする。

## Applicability/Limits

外部 archive、remote branch、publish artifact の readback に適用する。単一 checkout 内の
read-only診断には過剰な場合があるが、外部共有や closeout の成功条件を緩める理由にはならない。
raw event 本体は runtime log archive owner に置く。

## Evidence/Source

AgentCanon main base の runtime archive lifecycle と closeout/readback route を、
`documents/runtime/runtime-log-archive.md` の canonical archive contract と照合した。

## Promoted Owner Refs

- `documents/runtime/runtime-log-archive.md`

## Related Records

- なし
