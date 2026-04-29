# Workflow Monitoring
<!--
@dependency-start
responsibility Documents Workflow Monitoring for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines staged workflow and closeout gates
upstream design ../workflows/agent-learning-workflow.md defines feedback and self-improvement capture
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates monitoring evidence
@dependency-end
-->


- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

## Signals

<!-- Record workflow signals observed during execution: selected skills, stage owners, subagent or parent-direct routing, MCP preflight, repo dependency intake, web-research decision, review status, validation status, and any drift risk. Use explicit opt-out markers such as mcp_preflight_not_required only when the workflow made that decision. -->

## Interventions

<!-- Record monitoring-driven interventions: spawned or skipped roles, added review gates, dependency-tool reruns, prompt/tool/config corrections, schedule changes, or explicit no-op decisions. -->

## Improvement Decisions

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- memory_learning_decision: pending

<!-- Use applied, recorded, or not_applicable. Do not leave pending at closeout. If applied or recorded, cite the concrete file, commit, or memory entry. -->
