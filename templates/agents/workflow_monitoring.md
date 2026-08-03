# Workflow Monitoring（workflow 監視）
<!--
@dependency-start
contract workflow
responsibility Documents Workflow Monitoring for this repository.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines staged workflow and closeout gates
upstream design ../../agents/workflows/agent-learning-workflow.md defines feedback and self-improvement capture
downstream implementation ../../tools/agent_tools/workflow_monitor.py appends canonical monitoring and measurement entries
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates monitoring evidence
downstream implementation ../../tools/agent_tools/tool_rejection_preflight.py predicts pre-edit rejection gates
@dependency-end
-->


- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

{{>reader_map}}

## Signals（signal）

<!-- 実行中に観測した workflow signal を記録します。手編集より `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --signal "..."` と tool-level `--report-dir` hook を優先します。selected skill、stage owner、subagent/parent-direct routing、wave_id、repo dependency intake、web-research decision、review status、validation status、drift risk を含めます。run-bundle producer は `workflow_monitor.py` を通じて canonical な `runtime_measurement_input=<JSON>` signal を出力するため、null と明示的 zero を区別し、その record を手書き・重複しません。 -->

- failure-cause classification:
- conflict intent / preserved user or design clause:
- unexpected action report and parent handoff:
- cleanup/materialization readback:

## Behavior Events（behavior event）

<!-- 観測可能な agent behavior を retrospective prose ではなく structured event として記録します。`workflow_monitor.py --behavior-event "..."` を優先します。skill invocation、wave_id 付き stage/subagent routing、mid-task expansion、budget before/after、spawned/skipped role と理由、実装を gate する tool call、skill 使用時の EVAL_RUN_ID/EVAL_USED_SKILLS/EVAL_ACCUMULATED_REPORT、dependency/static-analysis、code checker、pre-edit rejection prediction、hook/tool feedback、protocol update、token efficiency、runtime feedback、subagent no-return investigation、static-analysis feedback、execution path、route efficiency、review decision、feedback action、subagent closeout、diff-check approval を必要 event family とします。実利用 feedback で skill/workflow/eval/memory を更新する場合は `workflow_monitor.py --runtime-feedback "source=user target=<skill-or-workflow> action=prompt_repair"` を使います。runtime_feedback=observed かつ action が no_op でなければ、closeout 前に下の Improvement Decisions を少なくとも 1 つ applied または recorded にします。 -->

## Actual Wave Events（実際の wave event）

<!-- selected schedule.md Agent Wave Ledger event を簡潔な `wave_event=...` token row として mirror し、dynamic expansion を検索・確認可能にします。各 row に wave_id、event_kind、spawn_authority、trigger、budget_before/after、runtime_max_threads/depth、spawned_roles、role_instances、skipped_roles、allowed_paths、do_not_read、write_scope、validation_route、review_gate、handoff_artifacts、status を記録します。同一 role を区別する deterministic ledger は `role_id:instance_id:agent_type:input_packet` を使います。mid-task user input では input_classification、updated_packet、redispatch_action、target_agents、scope_status、lifecycle_policy_ref を追加し、subagent no-return investigation では agent_id、wait_status、last_known_status、evidence_pointer、resolution_decision を追加します。durable evidence が必要なら手編集より `workflow_monitor.py --mid-task-user-input` を優先します。 -->

## Tool Warnings（tool warning）

- tool_warnings_status: pending

<!-- non-blocking tool、hook、checker、wrapper、guardrail が warning を出したら、直ちに `workflow_monitor.py --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"` で記録します。修正後は同じ warning_id を `status=resolved evidence=<path-or-command>` で記録します。normal warning は resolved、durable owner 付き deferred_with_issue、または明示 approval evidence と durable rationale artifact 付き accepted_with_reason で終了し、fix-now/S0/S1 は resolved にします。warning がなければ `workflow_monitor.py --tool-warning-status none` を実行し、closeout で pending を残しません。 -->

## Interventions（介入）

<!-- monitoring が促した intervention を記録します。closeout だけでなく run 中に Eval evidence を蓄積するため `workflow_monitor.py --intervention "..."` を優先します。spawned/skipped role、追加 review gate、dependency-tool rerun、prompt/tool/config correction、schedule change、明示的 no-op decision を含めます。 -->

## Improvement Decisions（改善判断）

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- memory_learning_decision: pending

<!-- applied、recorded、not_applicable のいずれかを使います。`workflow_monitor.py --decision key=value` を優先し、closeout に pending を残しません。applied/recorded なら具体的な file、commit、memory entry を引用します。runtime_feedback=observed かつ action が no_op でなければ、全 decision を not_applicable のままにしません。 -->
