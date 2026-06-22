# Workflow Monitoring
<!--
@dependency-start
contract workflow
responsibility Documents Workflow Monitoring for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines staged workflow and closeout gates
upstream design ../workflows/agent-learning-workflow.md defines feedback and self-improvement capture
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates monitoring evidence
downstream implementation ../../tools/agent_tools/tool_rejection_preflight.py predicts pre-edit rejection gates
@dependency-end
-->


- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

## Signals

<!-- Record workflow signals observed during execution. Prefer `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --signal "..."` and tool-level `--report-dir` hooks over hand edits. Required signals include selected skills, stage owners, subagent or parent-direct routing, wave_id, repo dependency intake, web-research decision, review status, validation status, and any drift risk. -->

## Behavior Events

<!-- Record observable agent behavior as structured events, not retrospective prose. Prefer `workflow_monitor.py --behavior-event "..."`. Required event families include skill invocation, stage/subagent routing with wave_id, mid-task expansion trigger, budget before/after, spawned/skipped roles and rationale, tool calls that gate implementation, accumulated prompt eval run status with EVAL_RUN_ID, EVAL_USED_SKILLS, and EVAL_ACCUMULATED_REPORT whenever a skill is used, dependency/static-analysis runs, code checker results such as `tool_call=pyright code_checker=pass`, `tool_call=ruff code_checker=pass`, `tool_call=oop-readability-check code_checker=pass`, or explicit `code_checker_not_required`, pre-edit tool rejection prediction with `pre_edit_rejection_prediction=reviewed` and `predicted_tool_rejection_gates=<recorded|none>`, hook/tool feedback routing with `hook_tool_feedback=reviewed`, `parent_protocol_update=<applied|recorded|not_required>`, `subagent_protocol_update=<applied|recorded|not_required>`, and `protocol_feedback_reason=...`, token-efficiency protocol activation or explicit opt-out, token footprint comparison, runtime_feedback=observed or runtime_feedback_not_observed, subagent_no_return_investigation with agent_id, wave_id, cause evidence, and resolution decision, static_analysis_feedback=applied|recorded|not_applicable, execution_path=..., route_efficiency=..., selected_inefficient_route=..., review decisions, feedback actions, subagent lifecycle closeout, and diff-check approval. Use `workflow_monitor.py --runtime-feedback "source=user target=<skill-or-workflow> action=prompt_repair"` when feedback from actual use should update skill prompts, workflow prompts, evals, or memory. If runtime_feedback=observed and action is not no_op, at least one Improvement Decisions line below must be applied or recorded before closeout. -->

## Actual Wave Events

<!-- Mirror schedule.md Agent Wave Ledger events as concise `wave_event=...` token rows so dynamic expansion is searchable and checkable. Required tokens for each row: wave_id, event_kind, spawn_authority, trigger, budget_before, budget_after, runtime_max_threads, runtime_max_depth, spawned_roles, role_instances, skipped_roles, allowed_paths, do_not_read, write_scope, validation_route, review_gate, handoff_artifacts, status. `spawned_roles` is the legacy aggregate; `role_instances` is the deterministic identity ledger using `role_type:instance_id:input_packet` entries so same-role subagents remain distinguishable. For `event_kind=mid_task_user_input`, also include input_classification, updated_packet, redispatch_action, target_agents, scope_status, and lifecycle_policy_ref. For `event_kind=subagent_no_return_investigation`, include agent_id, wait_status, last_known_status, evidence_pointer, and resolution_decision. `scope_or_contract_change` also includes fresh_wave_evidence; `new_task` also includes fresh_run_bundle. Prefer `workflow_monitor.py --mid-task-user-input` instead of hand editing. -->

## Tool Warnings

- tool_warnings_status: pending

<!-- If any non-blocking tool, hook, checker, wrapper, or guardrail emits a warning, record it immediately with `workflow_monitor.py --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"`. Record the same warning_id again with `status=resolved evidence=<path-or-command>` after repair. Normal warnings reach tool_warning_exit_status through resolved, deferred_with_issue issue=<issue-path-or-pr> with durable owner, or accepted_with_reason with explicit_approval_evidence and a durable rationale artifact; fix-now / S0 / S1 warnings must be `resolved`. If no warnings were observed, run `workflow_monitor.py --tool-warning-status none`. Do not leave this section pending at closeout. -->

## Interventions

<!-- Record monitoring-driven interventions. Prefer `workflow_monitor.py --intervention "..."` so Eval evidence is accumulated during the run, not only at closeout. Include spawned or skipped roles, added review gates, dependency-tool reruns, prompt/tool/config corrections, schedule changes, or explicit no-op decisions. -->

## Improvement Decisions

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- memory_learning_decision: pending

<!-- Use applied, recorded, or not_applicable. Prefer `workflow_monitor.py --decision key=value`. Do not leave pending at closeout. If applied or recorded, cite the concrete file, commit, or memory entry. If runtime_feedback=observed and action is not no_op, all decisions cannot remain not_applicable. -->
