# Documentation And Design Trace Audit Unit
<!--
@dependency-start
contract design
responsibility Audits reader navigation, design correspondence, Markdown correctness, and canonical-document separation.
upstream design ../README.md owns source/evidence boundary
upstream design ../../design/README.md owns design-canon reader route
upstream implementation ../../../agents/skills/long-form-writing.md owns reader-facing document repair
downstream implementation ../../../agents/skills/md-style-check.md owns Markdown formatter and checks
@dependency-end
-->

## Reader Map

長文は先頭の Reader Map、次に design claim、読者向け手順、formatter evidence の順で読みます。
README、documents、AGENTS、design、skill の route が一つの正本へ辿れることを確認し、
generated report と canonical document を混同しません。

## Owner Responsibility

`long-form-writing` が reader-facing prose と design trace の修正を所有し、`md-style-check`
が Markdown、math、Mermaid、link の formatter/check を所有します。

## Invariant

各長文文書は目的、前提、手順、検証を単体で読め、README/index から正本へ到達できる。
stale path、旧 helper、重複 checklist、壊れた heading/list/code/link、design と実装の
trace drift がない。

## Evidence Sources

- root と directory の `README.md`、`documents/README.md`
- `documents/design/` の target state と correspondence
- `tools/docs/` と Markdown/math/Mermaid formatter
- `check_design_doc_claims.py`
- 変更後の link/readback と docs-check output

## Repair Route

owner skill は `long-form-writing`、formatter は `md-style-check`。既存 canonical document
へ統合または参照し、generated inventory/report を第二の policy source にしません。

## Validation

変更 Markdown の heading/list/link、math、Mermaid、design claim、reader path を対象に
formatter と static checker を実行します。無関係な全 repo prose lint は追加しません。

## Close Condition

正本と参照が一意で、変更文書の formatter/readback が pass し、design-to-implementation
trace が対象責務を覆う。legacy checklist の全移行IDが対応 unit に一度だけ存在する。

## Related Change Surfaces

`surface:docs.design-trace`、`surface:docs.reader-map`、`surface:docs.formatter`。design、
README、Markdown formatter、audit canon の change surface を変更したときだけ本 unit を更新します。

## Legacy Migration IDs

PRA-C033 PRA-C034 PRA-C035 PRA-C036 PRA-C037 PRA-C038 PRA-C039 PRA-X022 PRA-X023 PRA-X024 PRA-X025
