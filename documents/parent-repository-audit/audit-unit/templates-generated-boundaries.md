# Templates And Generated Boundaries Audit Unit
<!--
@dependency-start
contract design
responsibility Audits templates, generated artifacts, reports, memory, notes, and source/evidence separation.
upstream design ../README.md owns canonical source versus generated evidence boundary
upstream design ../../rule/README.md owns document placement rules
upstream implementation ../../../agents/skills/document-canon-cleanup.md owns stale and duplicate document repair
downstream implementation ../../../agents/skills/result-artifact-writeout.md owns durable evidence writeout
@dependency-end
-->

## Reader Map

template、generated inventory/report、run bundle、memory、notes、state の classification を
先に行い、canonical source を探してから必要な artifact を読む。generated summary/index は
projection として扱い、監査判定をそこへ移さない。

## Owner Responsibility

`document-canon-cleanup` が文書の正本/非正本分類と重複整理を所有し、`result-artifact-writeout`
が必要な evidence/report の保存形式を所有します。

## Invariant

template は利用側の初期 surface だけを定義し、generated report、inventory、eval、memory、
notes、state、run bundle は canonical policy を上書きしない。artifact の保存先と source
path が明示され、source と parent-specific evidence が分離される。

## Evidence Sources

- `templates/`、`reports/`、`evidence/`、`memory/`、`notes/`、`.state/`
- `documents/rule/README.md`
- `document-canon-cleanup` の inventory result
- `result-artifact-writeout` の artifact manifest
- `reports/agents/<run-id>/` の closeout evidence

## Repair Route

owner skill は `document-canon-cleanup`、artifact は `result-artifact-writeout`。重複 policy
は正本 owner へ戻し、generated file を手編集して canonical source にしません。

## Validation

path classification、source link、artifact manifest、重複/legacy document inventory を static
に確認します。artifact producer の runtime 実行は保存契約を静的に確定できない場合だけです。

## Close Condition

canonical source、parent evidence、generated projection の分類が一意で、必要な artifact の
path/manifest/readback が pass し、旧 checklist の二重正本が残っていない。

## Related Change Surfaces

`surface:templates.generated-boundary`、`surface:evidence.artifacts`、`surface:docs.canon`。
template、artifact schema、generated projection、document placement の変更時だけ本 unit を更新します。

## Legacy Migration IDs

PRA-M01 PRA-M02 PRA-M03 PRA-M04 PRA-M05 PRA-M06 PRA-M07 PRA-M08 PRA-C043 PRA-C044 PRA-C045 PRA-C046 PRA-C079 PRA-C080 PRA-C081 PRA-C082 PRA-C083 PRA-C084 PRA-C085 PRA-C086 PRA-C101 PRA-C106 PRA-C107 PRA-C108 PRA-C109 PRA-C110 PRA-X027 PRA-X045 PRA-X046
