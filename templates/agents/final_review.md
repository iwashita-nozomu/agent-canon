# Final Review（最終レビュー・selected escalation）
<!--
@dependency-start
contract template
responsibility Documents Final Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/design/dependency-manifest-design.md dependency review policy
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

## Ship Blockers（出荷を止める指摘）

| Finding | Severity | Status |
| ------- | -------- | ------ |

## Design Trace Acceptance（design trace の受入れ）

<!-- この artifact は final escalation または独立した unresolved claim/risk が選択された場合だけ materialize します。final diff が Abstract Design Frame、approved design section、user-request clause ID、Implementation Source Packet entry、test design が有効な場合の test-plan item に trace できるか確認します。 -->

## Design Side-Effect Trace Acceptance（design side-effect trace の受入れ）

<!-- 実装した副作用が approved Design Side-Effect Map と一致するか確認します。documents、workflows、prompt/config、validation output、dependency manifest、user-facing surface を含めます。後段へ移した、escalate した、または reviewer が明示的に受け入れた side-effect item を記録します。 -->

## Planned Work Completion Review（planned work 完了レビュー）

<!-- planned work unit と active clause がすべて完了し、schedule.md が全 TODO surface を反映し、work_log.md が意味のある実行履歴を示すか確認します。chunk、slice、checkpoint、subpass だけが完了していれば required_change とします。 -->

## Cross-Doc Coverage Review（文書横断 coverage レビュー）

<!-- task が 1 つの document tree branch に閉じず、受入れ前に関連 cross-cutting packet docs を考慮したか確認します。task に影響する review policy、guardrail、lifecycle docs、migration/integration docs を無視していれば revise とします。 -->

## Spec-To-Product Coverage Review（spec から product への coverage レビュー）

<!-- すべての must-do と completion-evidence clause について、それを満たす実装 surface または artifact を確認します。requested spec に対応する implementation、doc、test、command、または明示的な deferred/rejected clause がなければ revise とします。 -->

## Review Finding Incorporation Review（review finding 反映レビュー）

<!-- selected owning review gate と明示的に有効化した specialist finding が implementation に反映されたか、または明示的に escalate されたか確認します。reviewer output は仮説入力であり、accepted finding には current snapshot、reachable path、contract、witness/static proof が必要です。rejected finding は reason_code/evidence_ref を持ち、repair wave を作りません。 -->

## Review Rejection Response Review（reject 応答レビュー）

<!-- review rejection、requested-change、revise、required_change の応答が active request clause と approved design intent を保持したか確認します。withdrawal、supersession、owner-boundary、unsafe-replacement、escalation evidence なしに rollback、discard、requested behavior の narrowing で green state にした場合は revise とします。 -->

## Semantic Search And Responsibility Evidence（semantic search と責務証拠）

<!-- この task に review-time semantic-index artifact が必要だったか確認します。存在すれば responsibility-scoped merge candidate、thin-doc candidate、long-query search hit を accepted、fixed、rejected にした根拠を記録します。関連 candidate を無視した場合、または dependency/structure evidence なしに semantic output だけを merge/delete authority にした場合は revise とします。 -->

## Post-Fix Full Review Rerun Review（修正後 full review rerun）

<!-- accepted review-driven fix が behavior、owner/design boundary、correctness、validation、publication state を変えた場合、latest diff に対して selected owning gate を rerun したか確認します。full review rerun は touched contract が要求する final candidate に限り選択します。 -->

## Repo-Wide Dependency Review（repo-wide dependency レビュー）

<!-- latest accepted fix 後に selected static/targeted validation route を確認します。full repository dependency review は final candidate contract が要求するときだけ実行します。 -->

## Canonical Tree-Head Acceptance（canonical tree head の受入れ）

<!-- tracked tree に残る durable product state が canonical path の current tree head だけか確認します。non-canonical design document、copied implementation、dated snapshot、backup path、mirrored tree が残れば revise とします。 -->

## Residual Risks（残存リスク）

<!-- 残存リスク、承認メモ、escalation point を記録します。 -->

{{>decision_approve_revise_escalate}}
