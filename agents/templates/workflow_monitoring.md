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

<!-- Record observable agent behavior as structured events, not retrospective prose. Prefer `workflow_monitor.py --behavior-event "..."`. Required event families include skill invocation, stage/subagent routing, tool calls that gate implementation, accumulated prompt eval run status with EVAL_RUN_ID, EVAL_USED_SKILLS, and EVAL_ACCUMULATED_REPORT whenever a skill is used, dependency/static-analysis runs, code checker results such as `tool_call=pyright code_checker=pass`, `tool_call=ruff code_checker=pass`, `tool_call=oop-readability-check code_checker=pass`, or explicit `code_checker_not_required`, hook/tool feedback routing with `hook_tool_feedback=reviewed`, `parent_protocol_update=<applied|recorded|not_required>`, `subagent_protocol_update=<applied|recorded|not_required>`, and `protocol_feedback_reason=...`, token-efficiency protocol activation or explicit opt-out, token footprint comparison, runtime_feedback=observed or runtime_feedback_not_observed, static_analysis_feedback=applied|recorded|not_applicable, execution_path=..., route_efficiency=..., selected_inefficient_route=..., review decisions, feedback actions, subagent lifecycle closeout, and diff-check approval. Use `workflow_monitor.py --runtime-feedback "source=user target=<skill-or-workflow> action=prompt_repair"` when feedback from actual use should update skill prompts, workflow prompts, evals, or memory. -->

## Interventions

<!-- Record monitoring-driven interventions. Prefer `workflow_monitor.py --intervention "..."` so Eval evidence is accumulated during the run, not only at closeout. Include spawned or skipped roles, added review gates, dependency-tool reruns, prompt/tool/config corrections, schedule changes, or explicit no-op decisions. -->

## Improvement Decisions

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- memory_learning_decision: pending

<!-- Use applied, recorded, or not_applicable. Prefer `workflow_monitor.py --decision key=value`. Do not leave pending at closeout. If applied or recorded, cite the concrete file, commit, or memory entry. -->
