# Audit Evidence And Closeout Audit Unit
<!--
@dependency-start
contract design
responsibility Audits audit metadata, finding closure, run evidence, and truthful completion status.
upstream design ../README.md owns sequential unit closure and generated evidence boundary
upstream design ../../design/parent-repository-audit.md owns migration ledger and failure semantics
upstream implementation ../../../agents/skills/tool-finding-report.md owns raw/structured finding evidence
downstream implementation ../../../agents/skills/result-artifact-writeout.md owns durable closeout artifacts
@dependency-end
-->

## Reader Map

監査対象、branch、commit、監査者、結果、evidence、finding route、修正 readback、unit close、
全体 closeout の順に読みます。report は unit canon の projection であり、未実行 command を
成功扱いしないことを最後に確認します。

## Owner Responsibility

`tool-finding-report` が raw/structured finding と repair receipt を所有し、
`result-artifact-writeout` が必要な run bundle、closeout、retention を所有します。親監査
skill が unit の sequential closure coordinator です。

## Invariant

各 unit は pass、または finding→owner repair→対象 readback→closed、または typed
repair_blocked のいずれかを持つ。finding で全監査を abort せず次 unit を処理し、未完了
blocked を pass に昇格しない。metadata、command、結果、証拠の source が追跡できる。

## Evidence Sources

- audit metadata と stable migration ID
- `parent_repository_audit.py list/check` packet
- owner worker の repair/readback receipt
- `reports/agents/<run-id>/`、`verification.txt`、`closeout_gate.md`
- `tool-finding-report` と `result-artifact-writeout` の schema

## Repair Route

owner skill は `tool-finding-report` と `result-artifact-writeout`、coordinator は
`parent-repository-audit`。finding は該当 unit の owner skill/worker へ routing し、対象
path を readback して close receipt を作ってから次 unit へ進みます。

## Validation

metadata completeness、unit closure ledger、finding status、repair/readback evidence、
最終 status の consistency を static に確認します。runtime validation は unit が指定した
必要十分な command のみで、全 suite や別の checker を追加しません。

## Close Condition

全 selected unit に pass または closed/blocked receipt があり、blocked は最終 status に
反映され、metadata と completion report が実行実績を正確に記述する。legacy ID は一度だけ
対応 unit に存在し、generated summary は再生成可能な projection である。

## Related Change Surfaces

`surface:audit.evidence-closeout`、`surface:finding.repair`、`surface:run-bundle.closeout`。
audit result schema、finding/receipt schema、closeout gate、metadata の変更時だけ本 unit を更新します。

## Scope Patterns

- `pattern:reports/**`
- `pattern:evidence/**`
- `pattern:notes/**`
- `pattern:.state/**`
- `pattern:.agent-canon/**`
- `pattern:workspace/**`
- `pattern:goal.md`
- `pattern:README.md`

## Legacy Migration IDs

PRA-M01 PRA-M02 PRA-M03 PRA-M04 PRA-M05 PRA-M06 PRA-M07 PRA-M08 PRA-C043 PRA-C044 PRA-C045 PRA-C046 PRA-C080 PRA-C081 PRA-C082 PRA-C083 PRA-C084 PRA-C085 PRA-C101 PRA-C106 PRA-C107 PRA-C108 PRA-C109 PRA-C110 PRA-X027
