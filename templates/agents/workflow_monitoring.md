# Historical Workflow Monitoring

This schema describes archived reports consumed by explicit Eval. New tasks use
Codex collaboration, Git and the conversation; they do not create this file.
<!--
@dependency-start
contract workflow
responsibility Documents historical monitoring fields consumed by explicit run evaluation.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines staged workflow and closeout gates
upstream design ../../agents/skills/agent-learning.md defines feedback and self-improvement capture
upstream design ../../documents/runtime/task-contract-observation.md defines task contract observation schema and terminal coverage
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/run_evaluation.rs evaluates monitoring evidence
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs predicts pre-edit rejection gates
@dependency-end
-->


- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

{{>reader_map}}

## Signals（signal）


- failure-cause classification:
- conflict intent / preserved user or design clause:
- unexpected action report and parent handoff:
- cleanup/materialization readback:

## Behavior Events（behavior event）


## Actual Tool And Agent Results（実際の tool / agent 結果）

<!-- 選択した実行経路と、実際の tool call・subagent launch・completion・failure を、既存の behavior event と native result を根拠に記録します。期待経路は Markdown の owner / Skill link から読みます。run manifest や monitor row だけから実行・完了を推定しません。経路差だけを failure としません。 -->

## Tool Warnings（tool warning）

- tool_warnings_status: pending


## Interventions（介入）


## Improvement Decisions（改善判断）

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- knowledge_learning_decision: pending
