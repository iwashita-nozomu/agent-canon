# Reproducibility Review（再現性レビュー）
<!--
@dependency-start
contract template
responsibility Documents Reproducibility Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}
{{>review_contract}}

{{>findings_required_change_table}}

## Focus（確認点）

- provenance と commit traceability
- exact command と seed
- environment capture
- 別の読者による rerun 可能性
