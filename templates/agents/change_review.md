# Change Review（変更レビュー）
<!--
@dependency-start
contract template
responsibility Documents Change Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/design/dependency-manifest-design.md dependency review policy
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

## Chunk Findings（chunk の指摘）

| Chunk | Finding | Severity | Status | Evidence |
| ----- | ------- | -------- | ------ | -------- |
<!-- `blocking`, `non-blocking`, `question`, `not-applicable`, and `accepted-risk` are finding-level statuses. -->

## Hypothesis Adjudication（仮説の判定）

| Hypothesis | Snapshot Ref | Reachable Input / Control Path | Contract Ref | Witness / Static Proof | Adjudication | Reason Code | Evidence Ref | Opens Rework Wave |
| ---------- | ------------ | ----------------------------- | ------------ | ---------------------- | ------------ | ----------- | ------------ | ----------------- |

<!-- reviewer output は仮説入力です。decision-owning reviewer は current snapshot、reachable path、contract、witness/static proof がそろい、behavior、owner/design boundary、correctness、validation、publication state のいずれかを変える仮説だけを受け付けます。却下行は reason_code と evidence_ref を使い、edit、revert、rollback、publication、新 wave を許可しません。 -->

## Reuse And Style Findings（reuse と style の指摘）

<!-- implementation が detailed design document に従い、既存 code、naming、tests、docs style を mirror しているか記録します。 -->

## Semantic Responsibility Candidate Review（意味的責務候補レビュー）

<!-- 存在する場合は `review_backlog_scan.sh` の `semantic_index_merge_candidates_*.jsonl`、`semantic_index_thin_docs_*.jsonl`、任意の `semantic_index_search_*.jsonl` を確認します。この diff に影響する同一責務の重複、統合候補、thin wrapper、隣接検索 hit を記録します。semantic-index output は advisory な review evidence とし、merge や deletion を要求する前に dependency review、exact search、structure check、source inspection で確認します。 -->

## Cross-Doc Coverage Review（文書横断 coverage レビュー）

<!-- implementer と reviewer が 1 つの workflow branch だけに依存せず cross-cutting packet を使ったか確認します。関連する review、guardrail、migration、lifecycle docs が implementation の根拠から抜けていれば revise とします。 -->

## Design-Base Implementation Review（design 起点の実装レビュー）

<!-- Abstract Design Frame と Implementation Source Packet を含む active-packet の 4 entry に対して、1 つの統合 responsibility-unit diff を確認します。各変更 slice が approved design section、Design Side-Effect Map、user-request clause ID、source/reuse document または code path、test design が有効な場合だけ test-plan item に trace することを確認します。scope が最寄りの file、helper、finding ではなく approved responsibility model から来ていることを確認します。source、generated、deletion の各 record は approved artifact、clause、owner、source/reuse path、dependency order、validation evidence に trace します。duplicate parser/writer path、file 単位だけの部分完了、test-first production behavior は revise、design drift または design gap は escalate とします。 -->

## Canonical Tree-Head Review（canonical tree head レビュー）

<!-- diff が design で宣言した canonical implementation path だけを更新し、non-canonical design doc、copied implementation、backup file、snapshot tree、alternate truth surface が tracked tree に残らないことを確認します。parallel state があれば revise とします。 -->

## Remaining Work Review（残作業レビュー）

<!-- これが chunk/slice/checkpoint だけでないか、planned work unit や active clause が残っていないか確認します。implementer が内部進捗を task completion と扱う場合は revise とします。 -->

## User Request Trace Review（user request trace レビュー）

<!-- diff が宣言された clause ID を満たすか、user が要求していない作業へ drift していないか記録します。 -->

## Repo-Wide Dependency Review（repo-wide dependency レビュー）

<!-- 最初に static と targeted check を実行します。selected final candidate contract が要求する場合だけ全 repository に `bash tools/agent_tools/run_repo_dependency_review.sh` を実行し、それ以外は targeted route と broad check を選ばなかった理由を記録します。 -->

## Revision Loop（改訂ループ）

<!-- behavior、owner/design boundary、correctness、validation、publication state を変える accepted finding だけを記録します。rejected hypothesis は reason_code/evidence_ref を保持し、新しい review wave を作りません。 -->

## Review Rejection Response Review（reject 応答レビュー）

<!-- revise / required_change / rejected diff / requested-change の処理が user-requested clause または approved design intent を保持するか確認します。単に revert、discard、requested behavior の縮小をした場合は revise とします。revert や discard が正当なら withdrawal / supersession / owner-boundary / unsafe-replacement / escalation authority と保持した clause を記録します。 -->

## Post-Review Fix Rerun Requirement（修正後 rerun 要件）

<!-- decision-owning reviewer が behavior、owner/design boundary、correctness、validation、publication state を変える finding を accepted と判定した場合、updated diff に対する selected owning gate の rerun を記録します。duplicate、stylistic、already-covered、evidence-free、unreachable、stale、private/incidental、out-of-scope、unproven design-conflict hypothesis は reason_code と evidence_ref を持ち、wave や rollback を開始しません。 -->

## Follow-Up（後続対応）

<!-- 次の chunk に進む前に implementer が改訂する内容を記録します。 -->

## Decision（判定）

<!-- `accept` is valid when no unresolved finding has status `blocking`; use
     `changes-required` only when a blocking finding remains. -->
