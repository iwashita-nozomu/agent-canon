# Schedule Review（schedule レビュー）
<!--
@dependency-start
contract template
responsibility Documents Schedule Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

## Stage Order Review（stage 順序レビュー）

<!-- stage の順序、dependency の現実性、rollback point を確認します。 -->

## Reviewer Separation Review（reviewer 分離レビュー）

<!-- plan review、detailed design review、document flow review が異なる agent に割り当てられているか確認します。 -->

## Subagent Adequacy Review（subagent 妥当性レビュー）

<!-- 選択した subagent が requirements、research、planning、design、implementation に適切か確認します。Agent Wave Ledger に spawn_budget、allowed_paths、do_not_read、write_scope、review_gate、closeout evidence path のいずれかがない場合は revise とします。 -->

## Completion Boundary Review（完了境界レビュー）

<!-- schedule が task-level completion と chunk、slice、checkpoint、subpass を分けるか確認します。active clause と planned work unit の解決前に user-facing completion が unlock される場合は revise とします。 -->

## Risks（リスク）

<!-- schedule のリスクと sequencing issue を記録します。 -->

## Revision Loop（改訂ループ）

<!-- planner が戻る stage、変更内容、承認を止める事項を記録します。 -->

{{>decision_approve_revise_escalate}}
