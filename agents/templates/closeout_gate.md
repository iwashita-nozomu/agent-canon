# Closeout Gate

<!--
@dependency-start
contract template
responsibility Documents Closeout Gate for this repository.
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
downstream design workflow_monitoring.md records in-workflow monitoring and self-improvement decisions
downstream design ../../documents/dependency-manifest-design.md defines dependency manifest evidence
@dependency-end
-->

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Reader Map

- This template owns the closeout evidence ledger that decides when user-facing completion may be unlocked.
- The top sections record gate status and unlock rules; the evidence sections then cover dependency manifests, static analysis, AgentCanon sync, spec coverage, review integration, document structure, tool warnings, subagent lifecycle, diff-check, tree-head, report placement, evaluation, logs, and final evidence.
- Verifiers and auditors should start with `## Gate Status` and `## Unlock Rule`, then fill only the evidence sections activated by the current run profile.
- For chunked reading, keep the status keys as the checklist anchor and open each evidence section only when its corresponding key is still pending.

## Gate Status

- verifier_status: pending
- auditor_status: pending
- required_reviews_complete: no
- validation_complete: no
- request_contract_complete: no
- all_planned_chunks_complete: no
- overall_delivery_complete: no
- unfinished_tasks_absent: no
- dependency_headers_complete: no
- repo_wide_dependency_tools_complete: no
- repo_wide_static_analysis_complete: no
- agent_canon_latest_complete: no
- make_ci_status: pending
- spec_product_coverage_complete: no
- review_findings_integrated: no
- post_fix_full_review_complete: no
- tool_warnings_resolved: no
- mechanical_completion_loop_complete: no
- subagents_closed: no
- diff_check_agent_complete: no
- canonical_tree_head_complete: no
- agent_evaluation_complete: no
- runtime_log_archive_synced: no
- commit_created: no
- push_completed: no
- user_completion_report: locked

## Unlock Rule

`user_completion_report` を `unlocked` にしてよいのは、少なくとも次を満たしたあとだけです。

- verifier_status: pass
- auditor_status: resolved
- required_reviews_complete: yes
- validation_complete: yes
- request_contract_complete: yes
- all_planned_chunks_complete: yes
- overall_delivery_complete: yes
- unfinished_tasks_absent: yes
- dependency_headers_complete: yes
- repo_wide_dependency_tools_complete: yes
- `repo_wide_static_analysis_complete`: `yes` for full static analysis, or `profile_selected` when the runtime profile selected targeted validation
- agent_canon_latest_complete: yes
- `make_ci_status`: `pass`, `targeted`, or `not_applicable` according to the active risk profile
- spec_product_coverage_complete: yes
- review_findings_integrated: yes
- post_fix_full_review_complete: yes
- tool_warnings_resolved: yes
- mechanical_completion_loop_complete: yes
- subagents_closed: yes
- diff_check_agent_complete: yes
- canonical_tree_head_complete: yes
- agent_evaluation_complete: yes
- runtime_log_archive_synced: yes
- commit_created: yes
- push_completed: yes

## Completion Boundary Evidence

<!-- Record why this is the whole user-request completion, not just a chunk, slice, checkpoint, or subpass completion. List all planned work units and active clauses as complete, confirm schedule.md remains the TODO source of truth, confirm no unfinished task / follow-up / validation / commit / push / canon-sync item remains in scope, and explain why closeout stays locked if work_log.md or TODO coverage is incomplete. -->

## Dependency Manifest Evidence

<!-- Confirm that every created or edited human-authored text file has a top-of-file @dependency-start / @dependency-end manifest block, or record the scan-tool classification reason and alternate manifest/design artifact for files that cannot carry such a block. Include output from check_dependency_headers.py, scan_dependency_headers.sh, check_dependency_header_format.sh, and check_dependency_graph.sh when dependency edges changed. During migration, record any pre-existing full-repo graph baseline separately and confirm this change introduced no new old-format header, self reference, reverse-edge gap, kind mismatch, or cycle. -->

## Repo-Wide Dependency Tool Evidence

<!-- During checkpoint and final review, run `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` against the full repository. Do not unlock closeout if only changed-file dependency checks were run. Record REPO_DEPENDENCY_REVIEW=pass and the checked path count. If any header is missing or invalid, fix it and rerun before unlock. -->

## Repo-Wide Static Analysis Evidence

<!-- Before user-facing completion, select static-analysis evidence from the active runtime profile and risk class. Use `make ci` or equivalent full-repo pyright/ruff evidence when the profile requires a full local confidence gate, such as Large delivery, explicit user-requested comprehensive validation, or an AgentCanon PR gate that defines full CI as equivalent evidence. For Routine docs, prompt/prose-only edits, and Focused code slices, record the targeted commands that match the changed paths, set `repo_wide_static_analysis_complete: profile_selected`, and set `make_ci_status: targeted` or `not_applicable` as appropriate. `make ci-quick` alone is not a substitute when the selected profile requires full CI. -->

## AgentCanon Latest And CI Gate Evidence

<!-- `agent_canon_latest_complete` must be `yes` before user-facing completion. In submodule repos, unrelated parent dirty state is allowed; what must be clean is the AgentCanon update surface: `vendor/agent-canon/`, the parent gitlink, `.gitmodules`, and AgentCanon-owned root symlink/copy views. Dirty or stale AgentCanon update-surface state is not an environment blocker and is not a valid reason to skip commit / push. For AgentCanon update-surface changes, commit AgentCanon work on a named branch, run `bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` when main must be merged in, open or update the AgentCanon PR, and rerun `make agent-canon-ensure-latest`. Rerun `make ci` only when the active risk profile selects full CI; otherwise record the profile-selected targeted validation and set `make_ci_status: targeted` or `not_applicable`. Documented environment/toolchain issues still require environment repair before user-facing completion when the selected validation cannot run. -->

- agent_canon_latest_command:
- agent_canon_latest_status:
- agent_canon_submodule_status:
- agent_canon_source_head:
- agent_canon_parent_pin:

## Spec-To-Product Coverage Evidence

<!-- For each must-do and completion-evidence clause, record the concrete product behavior, file, doc, test, command, or artifact that satisfies it. Do not unlock completion while any requested spec has no implemented product surface or explicit deferred/rejected clause. -->

## Review Finding Integration Evidence

<!-- Record every required review artifact and whether findings were fixed, escalated, or explicitly accepted as follow-up. Do not unlock completion while fix-now findings remain unapplied or unreviewed. -->

## Post-Fix Full Review Evidence

<!-- If any review-driven fix landed after an earlier review pass, record the refreshed full review artifact paths for the latest diff. If no post-review fixes occurred after the last full review pass, state that explicitly. -->

## Document Structure Evidence

<!-- For changed Markdown source files, classify the document route before closeout and list every changed Markdown source path in `document_structure_paths`. Record `document_split_decision` as `keep:<reason>`, `split:<new-owner-boundary>`, `merge:<target>`, `inline:<target-section>`, `rename:<new-path>`, or `not_applicable:format-only:<reason>`. For substantive document edits, record `document_structure_status: complete`, `structure_planning: complete`, `prose_graph: complete`, and the structure contract artifact. For typo / link / format-only edits, record `document_structure_status: skipped`, `structure_contract: skipped:<reason>`, `md_style_check: pass`, `format_only_reason`, and `document_split_decision: not_applicable:format-only:<reason>`. Generated run-bundle Markdown under reports/ is outside this source-document gate. -->

- document_structure_paths:
- document_structure_status:
- document_split_decision:
- structure_planning:
- prose_graph:
- structure_contract:
- md_style_check:
- format_only_reason:

## Tool Warning Evidence

<!-- Confirm that workflow_monitoring.md has a non-pending Tool Warnings ledger. If no warning appeared, record `tool_warning_monitoring_status: none`, `tool_warning_open_items: none`, and the evidence source. If warnings appeared, every warning_id must be resolved, accepted with a reason, or deferred with an issue; fix-now / S0 / S1 warnings must be resolved, not deferred. -->

- tool_warning_monitoring_status:
- tool_warning_open_items:
- tool_warning_resolution_evidence:

## Mechanical Completion Loop Evidence

<!-- Record each finalization loop iteration: planned work units and active clauses inspected, latest diff inspected, validation / dependency / static-analysis evidence checked, diff-check agent decision, fix-now findings applied, and the reason the loop stopped. Do not mark complete until no planned work, review finding, validation failure, dependency failure, static-analysis failure, commit / push item, canon-sync item, or follow-up decision remains in this task scope. -->

- mechanical_loop_iterations:
- mechanical_loop_open_items:
- mechanical_loop_stop_reason:
- mechanical_loop_planned_work_status:
- mechanical_loop_review_findings_status:
- mechanical_loop_validation_status:
- mechanical_loop_dependency_review_status:
- mechanical_loop_static_analysis_status:
- mechanical_loop_commit_push_status:
- mechanical_loop_canon_sync_status:
- mechanical_loop_follow_up_status:

## Subagent Lifecycle Evidence

<!-- Record run-local subagent lifecycle evidence before user-facing completion. New user requests must use fresh subagents, not send_input to agents created for prior tasks. Mid-task user instructions must be classified as same_active_task_delta, scope_or_contract_change, or new_task; same-task deltas need a run-bundle checkpoint and updated packet path before any run-local send_input, while scope changes need a fresh follow-up wave. Stage-wave agents that are no longer needed must be closed before closeout. `reuse_for_new_task` records policy and must be `forbidden`; `previous_task_subagent_reuse` records observed compliance and must be `none`. This section is intentionally about run-local subagents; if a repo-changing task used no subagents, record close_agent_evidence as parent_direct_no_subagents only with PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes and PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker> plus the run-bundle reason. For dynamic fanout, reconcile every schedule.md Agent Wave Ledger row with workflow_monitoring.md Actual Wave Events and closed run-local agent ids. If `wait_agent` timed out, returned empty status, or a final response was absent at a wave decision point, record the subagent no-return investigation fields before close, replacement, or escalation evidence. -->

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

## Diff-Check Agent Evidence

<!-- Record the read-only diff-check agent instance, input packet paths, latest diff range or commit, decision, findings disposition, and rerun evidence after any fix. Parent self-review is not sufficient for this field. -->

- diff_check_agent_role:
- diff_check_agent_decision:
- diff_check_latest_diff_ref:
- diff_check_artifact:

`diff_check_latest_diff_ref` は現在の tracked diff state を示す ref にします。clean tree では git `HEAD`、dirty tree では `task_close.py` が計算する `HEAD-dirty-<sha256>` 形式です。`diff_check_artifact` は run bundle 内の artifact path にします。その artifact の `## Diff-Check Review` には、少なくとも `diff_check_agent_role`、`diff_check_agent_decision`、`diff_check_latest_diff_ref`、`diff_check_read_only: yes`、`diff_check_independent_agent: yes`、`diff_check_findings_status` を記録します。

## Canonical Tree-Head Evidence

<!-- Record the canonical design-document paths and implementation paths left in the tracked tree, and state which non-canonical drafts, copied implementations, snapshots, mirrored directories, or backup files were deleted or confirmed absent. Do not unlock completion while the tree carries more than one durable truth surface. -->

## Report Artifact Placement Evidence

<!-- Before closeout, run task_close.py and let report_artifact_checks.py classify report placement. Also run generated_artifact_guard.py to reject mechanically regenerated roots left in the source tree. Tracked durable reports are allowed only when they are not regenerated tool output. Untracked or ignored report files are allowed only under the current `reports/agents/<run-id>/`; report files in older run bundles are archive/cleanup blockers, and regenerated roots such as `reports/dependency-review/` or `reports/agent-eval-runs/` must be deleted and rerun rather than recovered into another report. -->

- report_artifact_placement_status:
- report_artifact_outside_current_run_bundle:
- generated_artifact_guard_status:
- generated_artifact_guard_blockers:
- report_artifact_recovery_evidence:

## Agent Evaluation Evidence

<!-- Run tools/agent_tools/evaluate_agent_run.py --report-dir <this-run> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write and record the resulting agent_evaluation.md status, score, feedback actions, and learning capture decision. Do not unlock completion while evaluation_status is not pass or feedback_actions_resolved is not yes. The evaluation must include workflow_monitoring.md evidence for active signals, Behavior Events, interventions, and skill/config/workflow/memory improvement decisions. -->

## Runtime Log Archive Evidence

<!-- Archive the active run with `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>`, then `python3 tools/agent_tools/runtime_log_archive_git.py push`, and run `python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain` before user-facing completion. Use broad `sync` only when intentionally collecting accumulated runtime families. Do not unlock closeout while the archive is dirty, on the wrong `logs/<environment-key>-<chat-key>` branch, or contains foreign repo-key dirty paths or committed foreign repo-key trees. Record whether archive/push committed or was a no-op, and include the archive branch and repo key. -->

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

## Evidence

<!-- Record the exact verification artifact, review artifacts, commit, branch, and push evidence used to close the run. -->
