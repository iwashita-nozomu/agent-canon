# Workflow Monitoring（workflow 監視）
<!--
@dependency-start
contract workflow
responsibility Documents Workflow Monitoring for this repository.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines staged workflow and closeout gates
upstream design ../../agents/skills/agent-learning.md defines feedback and self-improvement capture
upstream design ../../documents/runtime/task-contract-observation.md defines task contract observation schema and terminal coverage
downstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py appends canonical monitoring and measurement entries
downstream implementation ../../tools/runtime/lifecycle/task_contract_observation.py validates and summarizes contract observations
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

<!-- 実行中に観測した workflow signal を記録します。手編集より `python3 tools/runtime/lifecycle/workflow_monitor.py --report-dir <run> --signal "..."` と tool-level `--report-dir` hook を優先します。selected Skill、actual tool/agent route、repo dependency intake、web-research decision、review status、validation status、drift risk を含めます。run-bundle producer は `workflow_monitor.py` を通じて canonical な `runtime_measurement_input=<JSON>` signal を出力するため、null と明示的 zero を区別し、その record を手書き・重複しません。 -->

- failure-cause classification:
- conflict intent / preserved user or design clause:
- unexpected action report and parent handoff:
- cleanup/materialization readback:

## Behavior Events（behavior event）

<!-- 観測可能な agent behavior を retrospective prose ではなく structured event として記録します。`workflow_monitor.py --behavior-event "..."` を優先します。skill invocation、actual subagent launch/completion/failure、tool call、dependency/static-analysis、code checker、pre-edit rejection prediction、hook/tool feedback、protocol update、token efficiency、runtime feedback、subagent no-return investigation、static-analysis feedback、execution path、route efficiency、review decision、feedback action、subagent closeout、diff-check approval を必要に応じて記録します。実利用 feedback で skill/workflow/eval/memory を更新する場合は `workflow_monitor.py --runtime-feedback "source=user target=<skill-or-workflow> action=prompt_repair"` を使います。runtime_feedback=observed かつ action が no_op でなければ、closeout 前に下の Improvement Decisions を少なくとも 1 つ applied または recorded にします。 -->

<!-- タスク中に契約、guardrail、warning、failure、rejection、conflict が実際に作動したら、手書きの要約ではなく `python3 tools/runtime/lifecycle/task_contract_observation.py --report-dir <run> --record "<key=value...>"` で `agent-canon.task-contract-observation.v1` event を追加します。contract_id、contract_source、phase、trigger、outcome、owner、evidence_ref、response を記録し、blocked/violated は同一 identity の次 sequence で satisfied または durable issue 付き deferred_with_issue へ閉じます。観測がなければ `contract_observation=none owner=manager reason=<slug>` を 1 行だけ記録します。closeout 前に同 tool を引数なしで実行し、`task_contract_observation_eval_status=pass`、`task_contract_observation_coverage=complete`、`task_contract_resolution=terminal`、`contract_archive_route=agent-canon-log:agent-reports` を生成させます。pass token を手書きして checker の代替にしません。raw prompt、hidden reasoning、secret、absolute local path は保存しません。 -->

## Actual Tool And Agent Results（実際の tool / agent 結果）

<!-- 選択した実行経路と、実際の tool call・subagent launch・completion・failure を、既存の behavior event と native result を根拠に記録します。期待経路は Markdown の owner / Skill link から読みます。run manifest や monitor row だけから実行・完了を推定しません。経路差だけを failure としません。 -->

## Tool Warnings（tool warning）

- tool_warnings_status: pending

<!-- non-blocking tool、hook、checker、wrapper、guardrail が warning を出したら、直ちに `workflow_monitor.py --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"` で記録します。修正後は同じ warning_id を `status=resolved evidence=<path-or-command>` で記録し、最終状態を `tool_warning_exit_status` として read back します。normal warning は resolved、durable owner 付き deferred_with_issue、または `explicit_approval_evidence` と durable rationale artifact 付き accepted_with_reason で終了し、fix-now/S0/S1 は resolved にします。warning がなければ `workflow_monitor.py --tool-warning-status none` を実行し、closeout で pending を残しません。 -->

## Interventions（介入）

<!-- monitoring が促した intervention を記録します。closeout だけでなく run 中に Eval evidence を蓄積するため `workflow_monitor.py --intervention "..."` を優先します。spawned/skipped role、追加 review gate、dependency-tool rerun、prompt/tool/config correction、schedule change、明示的 no-op decision を含めます。 -->

## Improvement Decisions（改善判断）

- skill_improvement_decision: pending
- config_improvement_decision: pending
- workflow_improvement_decision: pending
- knowledge_learning_decision: pending

<!-- applied、recorded、not_applicable のいずれかを使います。`workflow_monitor.py --decision key=value` を優先し、closeout に pending を残しません。applied/recorded なら具体的な file、commit、memory entry を引用します。runtime_feedback=observed かつ action が no_op でなければ、全 decision を not_applicable のままにしません。 -->
