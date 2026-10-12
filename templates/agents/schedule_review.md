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

<!-- Markdown links が示す想定担当と、実際に選択された role・native launch/completion/failure を分けて確認します。monitor row や想定経路だけから実行・完了を推定しません。経路差だけでは revise にしません。 -->

## Completion Boundary Review（完了境界レビュー）

<!-- completion claim が割り当てられた責務の実結果と validation evidence に支えられているか確認します。 -->

## Risks（リスク）

<!-- schedule のリスクと sequencing issue を記録します。 -->

## Revision Loop（改訂ループ）

<!-- planner に戻す必要がある責務、変更内容、未解決の阻害事項を記録します。 -->

{{>decision_approve_revise_escalate}}
