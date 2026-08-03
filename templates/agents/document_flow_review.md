# Document Flow Review（文書の読者経路レビュー）
<!--
@dependency-start
contract template
responsibility Documents Document Flow Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

{{>findings_area_table}}

## Top-Down Readthrough（上からの通読）

<!-- 最初の読者が後戻りせず文書を上から下へ読めるか確認します。 -->

## Term And Prerequisite Introduction（用語と前提の導入）

<!-- exact active-packet の Implementation Source Packet にある用語、仮定、前提が使用前に導入されているか確認します。design artifact path と packet entry ID を記録し、chat や schedule prose を authority にしません。 -->

## Section Order And Reader Path（節順と読者経路）

<!-- 節順が意図した読者経路を支え、主要な判断が implementation detail より前に現れるか確認します。 -->

## Reader-Visible Side Effects（読者可視の副作用）

<!-- exact active-packet の Design Side-Effect Map にある docs、workflow、prompt、CLI/help text、report、validation output を確認します。各指摘に packet entry と source reference を記録します。 -->

## Rewrite Targets（書き直し対象）

<!-- 文書を順序どおり読めるようにする具体的な書き直し箇所を記録します。 -->

## Revision Loop（改訂ループ）

<!-- 上からの読者経路を承認可能にするため designer が書き直す内容を記録します。 -->

{{>decision_approve_revise_escalate}}
