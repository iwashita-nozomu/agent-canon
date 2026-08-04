# Missing path owner resolution

record_id: `structure--missing-path-owner-resolution`
record_schema: `agent-canon.memory-record.v1`

## Problem/Symptom

要求された file、directory、root view、または generated artifact が tree に見つからない。
すぐ新規作成すると、既存 owner の責務を複製したり、source/view/generated の境界を壊したりする。

## Context/Trigger

実装、document edit、root sync、template projection の前に、想定 path がない、または
同名 path の責務が複数候補に見えるときに使う。

## Root Cause

path の不在を単純な未実装と解釈し、structure contract、owner map、submodule/root-view、
directory README、generated status を照合していない。結果として、正本ではない場所に新しい
契約を作る。

## Effective Resolution

まず structure contract と責務範囲を確認し、path を AgentCanon source、template root view、
generated artifact、project-local surface、personal runtime state のいずれかに分類する。
既存 owner が見つかったらその route で修理し、owner がない場合だけ design/structure gate を
通して新規 path の責務を定義する。

## Failed Approaches

- 近い directory に同名の second canon を作る。
- parent の occupied vendor checkout を直接修正する。
- README、closed report、検索結果だけを canonical owner として扱う。

## Applicability/Limits

repository structure と AgentCanon path ownership の triage に適用する。明らかな project-local
feature の新規 path を不必要に AgentCanon source へ移す手順ではない。分類後の編集は、選ばれた
owner の write authority と validation route に従う。

## Evidence/Source

main base の Missing File Or Path Triage と structure-refactor pre-task contract を照合し、
この topic の recurrence-shortening knowledge として抽出した。

## Promoted Owner Refs

- `agents/canonical/CODEX_WORKFLOW.md`
- `agents/skills/structure-refactor.md`

## Related Records

- なし
