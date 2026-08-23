# Closeout Gate（closeout gate）

<!--
@dependency-start
contract template
responsibility Documents Closeout Gate for this repository.
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
downstream design workflow_monitoring.md records in-workflow monitoring and self-improvement decisions
downstream design ../../documents/design/dependency-manifest-design.md defines dependency manifest evidence
@dependency-end
-->

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Reader Map（読者 map）

- この template は user-facing completion を unlock できる時点を判定する closeout evidence ledger を所有します。
- 冒頭で gate status と unlock rule を記録し、その後 dependency manifest、static analysis、AgentCanon sync、spec coverage、review integration、document structure、tool warning、subagent lifecycle、diff-check、tree-head、report placement、evaluation、log、最終 evidence を確認します。
- verifier と auditor は `## Gate Status` と `## Unlock Rule` から読み始め、current run profile が有効にした evidence section だけを埋めます。
- 分割して読む場合は status key を checklist anchor とし、対応 key が pending の section だけを開きます。

この artifact は、user-facing completion を unlock するための最終 readback を所有します。
現在の runtime profile が選んだ targeted validation と、選ばなかった full suite/full scan の
境界を分け、source/projection identity、failure response、cleanup の証拠を先に確認します。

## Gate Status（gate status）

- verifier_status: pending
- auditor_status: pending
- verifier_role_id: <verifier-child-role>
- verifier_runtime_agent_id: <runtime-agent-id>
- verifier_receipt_ref: runtime/verifier_receipt.json
- parent_mutation_status: no_parent_mutation
- parent_mutation_evidence_ref: runtime/parent_mutation_evidence.json
- required_reviews_complete: not_applicable
- validation_complete: no
- request_contract_complete: no
- all_planned_chunks_complete: no
- overall_delivery_complete: no
- completion_coverage_consumer: no
- mapping_error_sets_empty: no
- typed_owner_boundary_status: pending
- canonical_format_check_status: pending
- canonical_dispatcher_schema_status: pending
- validation_failure_response_status: pending
- unfinished_tasks_absent: no
- dependency_headers_complete: no
- repo_wide_dependency_tools_complete: no
- repo_wide_static_analysis_complete: no
- agent_canon_latest_complete: no
- review_findings_integrated: no
- focused_recheck_complete: not_applicable
- tool_warnings_resolved: no
- review_convergence_complete: no
- subagents_closed: no
- diff_check_agent_complete: not_applicable
- canonical_tree_head_complete: no
- agent_evaluation_complete: no
- runtime_log_archive_synced: no
- commit_created: no
- push_completed: no
- user_completion_report: locked
- algorithm_contract_before_tests: pending
- necessary_sufficient_oracle_boundary: pending
- failure_cause_classification_complete: no
- conflict_intent_readback: pending
- lifecycle_cleanup_complete: no
- clone_materialization_readback: pending
- unexpected_action_report: none

## Unlock Rule（unlock rule）

`user_completion_report` を `unlocked` にしてよいのは、少なくとも次を満たしたあとだけです。

- verifier_status: pass
- auditor_status: resolved
<!-- selected owning gate の判定が完了したら required_reviews_complete を yes にし、review が無効なら not_applicable にします。 -->
- validation_complete: yes
- request_contract_complete: yes
- all_planned_chunks_complete: yes
- overall_delivery_complete: yes
- unfinished_tasks_absent: yes
- dependency_headers_complete: yes
- repo_wide_dependency_tools_complete: yes
- `repo_wide_static_analysis_complete`: `yes` for full static analysis, or `profile_selected` when the runtime profile selected targeted validation
- agent_canon_latest_complete: yes
- completion_coverage_consumer: yes
- mapping_error_sets_empty: yes
- typed_owner_boundary_status: pass
- canonical_format_check_status: pass
- canonical_dispatcher_schema_status: pass
- validation_failure_response_status: pass
- review_findings_integrated: yes
<!-- repair 後の focused recheck が完了したら focused_recheck_complete を yes にし、initial review で blocker が無ければ not_applicable にします。 -->
- tool_warnings_resolved: yes
- review_convergence_complete: yes
- subagents_closed: yes
<!-- diff-check gate が有効で完了したら diff_check_agent_complete を yes にし、それ以外は not_applicable にします。 -->
- canonical_tree_head_complete: yes
- agent_evaluation_complete: yes
- runtime_log_archive_synced: yes
- commit_created: yes
- push_completed: yes
- algorithm_contract_before_tests: pass / not_applicable_with_reason
- necessary_sufficient_oracle_boundary: pass / not_applicable_with_reason
- failure_cause_classification_complete: yes
- conflict_intent_readback: pass / not_applicable
- lifecycle_cleanup_complete: yes
- clone_materialization_readback: pass / not_applicable
- unexpected_action_report: none / resolved / handed_to_parent

## Completion Boundary Evidence（完了境界 evidence）

<!-- これが chunk、slice、checkpoint、subpass ではなく user request 全体の完了である理由を記録します。planned work unit と active clause をすべて complete とし、schedule.md が TODO の source of truth であること、unfinished task/follow-up/validation/commit/push/canon-sync item が scope に残らないことを確認します。work_log.md または TODO coverage が不完全なら closeout を lock する理由を記録します。 -->

- completion_coverage_artifact: completion_coverage.json
- completion_coverage_schema: agent-canon.completion-coverage.v1
- completion_coverage_consumer: no
- control_topology_observation_ref:
- all_planned_chunks_complete_source: completion-boundary projection
- overall_delivery_complete_source: completion-boundary projection
- open_repairs:
- open_crossing_edges:
- canonical_gate_basis: G1_CLAUSE_COVERAGE,G2_OWNER_BOUNDARY,G3_STAGE_EVIDENCE,G4_VALIDATION_RESPONSE,G5_DELIVERY_BOUNDARY

## Dependency Manifest Evidence（dependency manifest evidence）

<!-- 作成・編集した human-authored text file がすべて top-of-file の @dependency-start/@dependency-end manifest block を持つことを確認します。持てない file は scan-tool classification reason と代替 manifest/design artifact を記録します。dependency edge が変わった場合は check_dependency_headers.py、scan_dependency_headers.sh、check_dependency_header_format.sh、check_dependency_graph.sh の output を含めます。migration 中は既存 full-repo graph baseline を別記録し、old-format header、self reference、reverse-edge gap、kind mismatch、cycle を新たに導入していないことを確認します。 -->

## Repo-Wide Dependency Tool Evidence（repo-wide dependency tool evidence）

<!-- checkpoint と final review では全 repository に `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を実行します。changed-file dependency check だけなら closeout を unlock しません。REPO_DEPENDENCY_REVIEW=pass と checked path count を記録し、header が missing/invalid なら修正して rerun します。 -->

## Canonical Formatter And Static Evidence（canonical formatter/static evidence）

<!-- canonical な Markdown/math/Mermaid formatter/check route 1 つと selected non-Python static evidence を記録します。重複する CI、formatter、checker、coverage、mutation、private-helper、checker-retest route は追加の W2 gate ではありません。 -->

- canonical_format_check_route: tools/bin/agent-canon docs check <changed-markdown-paths>
- canonical_format_check_status:
- selected_non_python_static_evidence:
- typed_owner_boundary_status:
- mapping_error_sets_empty:
- Markdown/math/Mermaid source paths:
- formatter/fixer command and post-format readback:
- targeted-only reason or selected full-suite owner:

## CompletionCoverage And Failure Response Evidence（completion coverage と failure response）

<!-- generated v1 projection、5 つの明示的 mapping error set、pointer-only validation-failure response を記録します。taxonomy text の owner は JSON source と generated Markdown reader のままです。 -->

- completion_coverage_artifact:
- completion_coverage_consumer:
- validation_failure_response_status:
- validation_failure_taxonomy_owner: documents/runtime/runtime-profiles-and-check-matrix.json
- validation_failure_taxonomy_reader: documents/runtime/runtime-profiles-and-check-matrix.md

## AgentCanon Latest Evidence（AgentCanon latest evidence）

<!-- `agent_canon_latest_complete` は repository-update evidence field です。2 つ目の W2 formatter や completion-coverage gate ではありません。 -->

- agent_canon_latest_command:
- agent_canon_latest_status:
- agent_canon_submodule_status:
- agent_canon_source_head:
- agent_canon_parent_pin:

## Spec-To-Product Coverage Evidence（spec から product への coverage evidence）

<!-- 各 must-do と completion-evidence clause について、それを満たす具体的な product behavior、file、doc、test、command、artifact を記録します。requested spec に implemented product surface または明示的 deferred/rejected clause がなければ completion を unlock しません。 -->

## Review Finding Integration Evidence（review finding 統合 evidence）

<!-- required review artifact と、finding を fixed、escalated、follow-up として明示的に accepted したかを記録します。fix-now finding が未適用または未 review の間は completion を unlock しません。 -->

## Focused Recheck Evidence（focused recheck evidence）

<!-- initial owning review が stable blocking finding ID を返し、その repair が入った場合だけ記録します。candidate epoch/digest、repaired finding IDs、repair が invalidated した evidence IDs、focused recheck verdict を固定し、full review を再開しません。 -->

- focused_recheck_candidate_epoch:
- focused_recheck_candidate_digest:
- focused_recheck_finding_ids:
- focused_recheck_invalidated_evidence_ids:
- focused_recheck_status:

## Document Structure Evidence（文書 structure evidence）

<!-- changed Markdown source file は closeout 前に document route を分類し、全 changed Markdown source path を `document_structure_paths` に列挙します。`structure_activation=required` は未決の owner/source/reader/layout/validation topology を選択した route、`structure_activation=not_required` は既存 topology を明示して行う bounded edit、`structure_activation=format_only` は formatter-only route です。`document_split_decision` は `keep:<reason>`、`split:<new-owner-boundary>`、`merge:<target>`、`inline:<target-section>`、`rename:<new-path>`、`not_applicable:format-only:<reason>` の形式で記録します。complete route は activation に応じた positive structure evidence を記録し、format-only は skipped、理由、`md_style_check: pass` を記録します。reports/ 配下の generated run-bundle Markdown はこの source-document gate の外です。 -->

- document_structure_paths:
- document_structure_status:
- structure_activation:
- document_split_decision:
- structure_planning:
- prose_graph_activation:
- prose_graph:
- structure_contract:
- structure_owner:
- structure_source:
- structure_reader:
- structure_layout:
- structure_validation_topology:
- md_style_check:
- format_only_reason:

## Tool Warning Evidence（tool warning evidence）

<!-- workflow_monitoring.md の Tool Warnings ledger が non-pending か確認します。warning がなければ `tool_warning_monitoring_status: none`、`tool_warning_open_items: none`、evidence source を記録します。warning があれば全 warning_id を resolved、理由付き accepted、issue 付き deferred のいずれかにし、fix-now/S0/S1 は deferred ではなく resolved にします。 -->

- tool_warning_monitoring_status:
- tool_warning_open_items:
- tool_warning_resolution_evidence:

## Lifecycle And Cleanup Evidence（lifecycle と cleanup evidence）

<!-- remote/source/readback identity が complete になった後だけ generated projection、temporary clone、run-local artifact、raw-log cleanup を記録します。typed hold condition は owner が解消するまで blocked のままです。 -->

- source/remote/materialization identities:
- generated artifacts retained:
- cleanup command and owner:
- reconstructibility readback:
- cleanup failure cause and typed hold:
- parent handoff for any unexpected action:

## Review Convergence Evidence（review convergence evidence）

<!-- `agent-canon.review-convergence.v1` の terminal projection を記録します。one initial owning review、stable blocker IDs、focused recheck、unresolved measure、selected validation、same-state/action cycle の不在を一度だけ判定します。zero blocker + zero unresolved request clause + selected validation pass/not_applicable で ship/handoff し、advisory improvement は現 task を再開しません。 -->

- convergence_schema: agent-canon.review-convergence.v1
- candidate_epoch:
- candidate_digest:
- initial_review_status:
- initial_blocking_finding_ids:
- focused_recheck_finding_ids:
- open_blocking_finding_ids:
- advisory_finding_ids:
- unresolved_request_clause_ids:
- unresolved_validation_ids:
- unresolved_measure_initial:
- unresolved_measure_final:
- selected_validation_status:
- same_state_action_repeated:
- terminal_state:
- new_epoch_reason:

## Subagent Lifecycle Evidence（subagent lifecycle evidence）

<!-- subagent または durable lifecycle route を選択した場合、user-facing completion 前に run-local subagent lifecycle evidence を記録します。各 user input を same_active_task_delta、scope_or_contract_change、new_task に分類し、owner、responsibility、context、write authority、validation route が compatible なら revised scope を含めて active agent を reuse します。fresh agent は independent review、disjoint write authority、incompatible owner/context、context integrity failure 用です。durable checkpoint と updated packet path は coordination/resumption に必要な場合だけ作り、terminal stage-wave agent は cleanup として close します。timeout、empty status、absent final response は指定された termination_action/write_scope/overlap/lifecycle gate に記録します。dynamic fanout では schedule.md Agent Wave Ledger と workflow_monitoring.md Actual Wave Events、terminal run-local agent id を reconcile します。wait_agent の timeout/empty status/response 欠落があれば no-return investigation field を記録し、新しい state evidence または明示的 cancellation まで lifecycle gate を incomplete にします。 -->

- fresh_subagents_required:
- reuse_for_new_task:
- previous_task_subagent_reuse:
- mid_task_user_input_status:
- same_task_delta_packet_evidence:
- agent_wave_ledger_status:
- planned_vs_actual_wave_status:
- dynamic_spawn_policy_status:
- no_return_investigation_status:
- no_return_agent_ids:
- no_return_cause_evidence:
- no_return_resolution_decision:
- subagent_closeout_status:
- open_subagent_instances:
- close_agent_evidence:

## Diff-Check Agent Evidence（diff-check agent evidence）

<!-- selected owning review gate（有効時だけ read-only diff-check instance）、input packet path、latest diff range/commit、decision、finding disposition、accepted same-owner fix 後の rerun evidence を記録します。reviewer output は仮説入力で decision-owning reviewer が判定します。accepted finding は current snapshot、reachable path、contract、witness/static proof を引用し、rejected finding は reason_code/evidence_ref を持ち wave や rollback を起こしません。 -->

- diff_check_agent_role:
- diff_check_agent_decision:
- diff_check_latest_diff_ref:
- diff_check_artifact:

`diff_check_latest_diff_ref` は現在の tracked diff state を示す ref にします。clean tree では git `HEAD`、dirty tree では `task_close.py` が計算する `HEAD-dirty-<sha256>` 形式です。`diff_check_artifact` は run bundle 内の artifact path にします。その artifact の `## Diff-Check Review` には、少なくとも `diff_check_agent_role`、`diff_check_agent_decision`、`diff_check_latest_diff_ref`、`diff_check_read_only: yes`、`diff_check_independent_agent: yes`、`diff_check_findings_status` を記録します。

## Canonical Tree-Head Evidence（canonical tree-head evidence）

<!-- tracked tree に残した canonical design-document path と implementation path を記録し、削除または absent を確認した non-canonical draft、copied implementation、snapshot、mirrored directory、backup file を記録します。tree に durable truth surface が複数ある間は completion を unlock しません。 -->

## Report Artifact Placement Evidence（report artifact placement evidence）

<!-- closeout 前に task_close.py を実行し、report_artifact_checks.py に report placement を分類させます。generated_artifact_guard.py も実行し、source tree に残った mechanically regenerated root を拒否します。tracked durable report は regenerated tool output でない場合だけ許可します。untracked/ignored report は current `reports/agents/<run-id>/` 配下だけを許可し、older run bundle の report は archive/cleanup blocker とします。`reports/dependency-review/` や `reports/agent-eval-runs/` などの regenerated root は別 report へ移さず削除して rerun します。 -->

- report_artifact_placement_status:
- report_artifact_outside_current_run_bundle:
- generated_artifact_guard_status:
- generated_artifact_guard_blockers:
- report_artifact_recovery_evidence:

## Agent Evaluation Evidence（agent evaluation evidence）

<!-- evaluation reviewer が `tools/agent_tools/evaluate_agent_run.py --report-dir <this-run> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` を実行し、生成した agent_evaluation.md の status、score、feedback action、learning capture decision を記録します。evaluation_status が pass でない、または feedback_actions_resolved が yes でない間は completion を unlock しません。evaluation は active signal、Behavior Events、intervention、skill/config/workflow/memory improvement decision の workflow_monitoring.md evidence を含めます。 -->

## Runtime Log Archive Evidence（runtime log archive evidence）

<!-- active run を `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>` で archive し、`python3 tools/agent_tools/runtime_log_archive_git.py push`、`python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain` を user-facing completion 前に実行します。蓄積 runtime family を意図的に集める場合だけ broad `sync` を使います。archive が dirty、誤った `logs/<environment-key>-<chat-key>` branch、foreign repo-key の dirty path/commit tree を含む場合は closeout を unlock しません。archive/push が commit したか no-op か、archive branch と repo key を記録します。 -->

- runtime_log_archive_sync_command:
- runtime_log_archive_sync_status:
- runtime_log_archive_check_clean_command:
- runtime_log_archive_check_clean_status:
- runtime_log_archive_repo_key:
- runtime_log_archive_branch:
- runtime_log_archive_branch_match:
- runtime_log_archive_dirty:
- runtime_log_archive_foreign_dirty:
- runtime_log_archive_foreign_dirty_keys:
- runtime_log_archive_foreign_tree:
- runtime_log_archive_foreign_tree_keys:
- runtime_log_archive_commit:
- runtime_log_archive_push:

## Evidence（証拠）

<!-- run を閉じるために使った exact verification artifact、review artifact、commit、branch、push evidence を記録します。 -->
