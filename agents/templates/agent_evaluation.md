# Agent Evaluation

<!--
@dependency-start
upstream design ../workflows/agent-learning-workflow.md agent feedback workflow
upstream design workflow_monitoring.md in-workflow monitoring artifact
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py generates concrete evaluations
downstream implementation ../../tools/agent_tools/task_close.py enforces pass status before user completion
@dependency-end
-->

- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

## Gate Status

- evaluation_status: pending
- score: 0
- max_score: 100
- threshold: 85
- feedback_actions_resolved: no
- learning_capture_complete: no

## Scope

<!-- Record the run bundle evaluated and whether the evidence came from workflow_monitoring.md, traces, run artifacts, review artifacts, validation logs, or user feedback. -->

## Rubric

| Criterion | Score | Max | Status | Feedback |
| --------- | ----- | --- | ------ | -------- |

## Feedback Actions

| Action ID | Severity | Action | Status |
| --------- | -------- | ------ | ------ |

## Learning Capture

<!-- Record whether durable agent-side observations should be logged with tools/agent_tools/log_agent_learning.py, and whether any skill/config/workflow change was applied or explicitly not_applicable. Do not paste raw chat. -->
