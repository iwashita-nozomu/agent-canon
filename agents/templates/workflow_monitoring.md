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

<!-- Record workflow signals observed during execution. Prefer `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --signal "..."` and tool-level `--report-dir` hooks over hand edits. Required signals include selected skills, stage owners, subagent or parent-direct routing, MCP preflight, repo dependency intake, web-research decision, review status, validation status, and any drift risk. Use explicit opt-out markers such as mcp_preflight_not_required only when the workflow made that decision. -->

## Behavior Events

<!-- Record observable agent behavior as structured events, not retrospective prose. Prefer `workflow_monitor.py --behavior-event "..."`. Required event families include skill invocation, stage/subagent routing, tool calls that gate implementation, prompt eval baseline/rerun status, dependency/static-analysis runs, review decisions, feedback actions, subagent lifecycle closeout, and diff-check approval. -->

## Interventions

<!-- Record monitoring-driven interventions. Prefer `workflow_monitor.py --intervention "..."` so Eval evidence is accumulated during the run, not only at closeout. Include spawned or skipped roles, added review gates, dependency-tool reruns, prompt/tool/config corrections, schedule changes, or explicit no-op decisions. -->

## Improvement Decisions

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- memory_learning_decision: pending

<!-- Use applied, recorded, or not_applicable. Prefer `workflow_monitor.py --decision key=value`. Do not leave pending at closeout. If applied or recorded, cite the concrete file, commit, or memory entry. -->
