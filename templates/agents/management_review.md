# Management Review（管理レビュー）
<!--
@dependency-start
contract template
responsibility Documents Management Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

## Scope Review（scope レビュー）

<!-- user intent、acceptance criteria、scope が十分に具体的か確認します。 -->

## User Request Coverage Review（user request coverage レビュー）

<!-- user_request_contract.md が must-do、must-not-do、completion-evidence の全 clause を silent drop なく収録するか確認します。 -->

## Source Bucket Review（source bucket レビュー）

<!-- 各 clause が current_request、durable_user_preference、repo_or_code_precedent、domain_or_external_constraint、unknown_or_open_question のいずれかで label され、durable preference が silent に task requirement へ変換されないか確認します。 -->

## Accumulated Context Resolution Review（蓄積 context の解決レビュー）

<!-- scope または判定を変える具体的な evidence がある場合だけ memory、notes/themes、notes/guardrails、notes/knowledge、notes/failures、documents、prior log、local code、test、必要な external constraint と照合します。decision に影響しない sweep は実行せず、未実行だけで revise にしません。 -->

## Unknown Handling Review（unknown 処理レビュー）

<!-- unknown_or_open_question が deferred または escalation entry にだけ現れ、active must-do、must-not-do、completion-evidence clause に現れないか確認します。蓄積 context で scope-changing unknown を解決できない場合だけ escalate とします。 -->

## Routing Review（routing レビュー）

<!-- workflow=<family>、skills=<...>、review=<...> が宣言され、適切な specialist role と明示的な stage subagent が有効か確認します。fanout ledger が Intake Responsibility Wave を total cap ではなく intake slice と証明しない場合、または dynamic expansion wave に budget/scope evidence がなければ revise とします。 -->

## Finding Status And Outcome（finding status と判定）

| Finding Status | Outcome impact |
| --- | --- |
| `blocking` | `changes-required` while unresolved |
| `non-blocking`, `question`, `not-applicable`, `accepted-risk` | visible evidence only; does not force changes |

<!-- management review is one owner gate; specialist checks remain bounded
validators and do not create duplicate full-review artifacts. -->

## Context And Library Sweep Review（context と library sweep レビュー）

<!-- planning 前に required document sweep、dependency/library sweep、existing-implementation sweep を実施し、artifact が inspected surface を記録するか確認します。 -->

## Reuse-First Review（reuse-first レビュー）

<!-- intake package が implementation の従う既存 code、docs、installed library を特定し、新規 path を提案する前に reuse/extension で足りない理由を記録するか確認します。 -->

{{>decision_approve_revise_escalate}}
