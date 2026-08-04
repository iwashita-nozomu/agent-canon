# Agent Evaluation（agent 評価）

<!--
@dependency-start
contract template
responsibility Documents Agent Evaluation for this repository.
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py generates concrete evaluations
downstream implementation ../../tools/agent_tools/task_close.py enforces pass status before user completion
@dependency-end
-->

- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

{{>reader_map}}

## Gate Status（gate status）

- evaluation_status: pending
- score: 0
- max_score: 100
- threshold: 85
- feedback_actions_resolved: no
- learning_capture_complete: no

## Scope（対象）

<!-- 評価した run bundle と、証拠が workflow_monitoring.md、trace、run artifact、review artifact、validation log、user feedback のどこから来たかを記録します。 -->

## Rubric（評価基準）

| Criterion | Score | Max | Status | Feedback |
| --------- | ----- | --- | ------ | -------- |

## Feedback Actions（feedback 対応）

| Action ID | Severity | Action | Status |
| --------- | -------- | ------ | ------ |

## Learning Capture（学習の保存）

<!-- durable な agent-side observation を tools/agent_tools/memory_record.py で記録するか、skill/config/workflow change を適用したか、明示的に not_applicable としたかを記録します。raw chat は貼り付けません。runtime feedback を観測し action が no_op でない場合は、適用または記録した improvement decision と具体的な target を引用します。 -->
