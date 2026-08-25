# Agent Evaluation（agent 評価）

<!--
@dependency-start
contract template
responsibility Documents Agent Evaluation for this repository.
upstream design ../../documents/runtime/task-contract-observation.md defines contract coverage and archive routing
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py generates concrete evaluations
downstream implementation ../../tools/agent_tools/task_contract_observation.py produces current-run contract coverage evidence
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
- task_contract_observation_eval_status: pending
- task_contract_observation_coverage: pending
- task_contract_resolution: pending
- contract_archive_route: pending

## Scope（対象）

<!-- 評価した run bundle と、証拠が workflow_monitoring.md、trace、run artifact、review artifact、validation log、user feedback のどこから来たかを記録します。task contract observation は contract_id、source、phase、final outcome、evidence_ref、response、agent-canon-log archive route を確認し、raw prompt や hidden reasoning を転記しません。 -->

## Rubric（評価基準）

| Criterion | Score | Max | Status | Feedback |
| --------- | ----- | --- | ------ | -------- |

## Contract Observation Coverage（契約観測 coverage）

| Observation ID | Contract ID | Source | Phase | Final Outcome | Evidence | Response |
| -------------- | ----------- | ------ | ----- | ------------- | -------- | -------- |

<!-- `task_contract_observation.py` の checker output と Behavior Events を参照します。blocked/violated の未解決、identity/sequence collision、observed と none の混在、checker を通さない pass token は fail とします。 -->

## Feedback Actions（feedback 対応）

| Action ID | Severity | Action | Status |
| --------- | -------- | ------ | ------ |

## Learning Capture（学習の保存）

<!-- durable な agent-side observation を agent-canon k/f で private log に記録するか、skill/config/workflow change を適用したか、明示的に not_applicable としたかを記録します。raw chat は貼り付けません。runtime feedback を観測し action が no_op でない場合は、適用または記録した improvement decision と具体的な target を引用します。 -->
