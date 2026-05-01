# Closeout Gate

<!--
@dependency-start
responsibility Documents Closeout Gate for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md closeout workflow contract
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
downstream design workflow_monitoring.md records in-workflow monitoring and self-improvement decisions
downstream design ../../documents/dependency-manifest-design.md defines dependency manifest evidence
@dependency-end
-->

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

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
- spec_product_coverage_complete: no
- review_findings_integrated: no
- post_fix_full_review_complete: no
- mechanical_completion_loop_complete: no
- subagents_closed: no
- diff_check_agent_complete: no
- canonical_tree_head_complete: no
- agent_evaluation_complete: no
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
- repo_wide_static_analysis_complete: yes
- spec_product_coverage_complete: yes
- review_findings_integrated: yes
- post_fix_full_review_complete: yes
- mechanical_completion_loop_complete: yes
- subagents_closed: yes
- diff_check_agent_complete: yes
- canonical_tree_head_complete: yes
- agent_evaluation_complete: yes
- commit_created: yes
- push_completed: yes

## Completion Boundary Evidence

<!-- Record why this is the whole user-request completion, not just a chunk, slice, checkpoint, or subpass completion. List all planned work units and active clauses as complete, confirm schedule.md remains the TODO source of truth, confirm no unfinished task / follow-up / validation / commit / push / canon-sync item remains in scope, and explain why closeout stays locked if work_log.md or TODO coverage is incomplete. -->

## Dependency Manifest Evidence

<!-- Confirm that every created or edited human-authored text file has a top-of-file @dependency-start / @dependency-end manifest block, or record the scan-tool classification reason and alternate manifest/design artifact for files that cannot carry such a block. Include output from check_dependency_headers.py, scan_dependency_headers.sh, check_dependency_header_format.sh, and check_dependency_graph.sh when dependency edges changed. During migration, record any pre-existing full-repo graph baseline separately and confirm this change introduced no new old-format header, self reference, reverse-edge gap, kind mismatch, or cycle. -->

## Repo-Wide Dependency Tool Evidence

<!-- During checkpoint and final review, run `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` against the full repository. Do not unlock closeout if only changed-file dependency checks were run. Record REPO_DEPENDENCY_REVIEW=pass and the checked path count. If any header is missing or invalid, fix it and rerun before unlock. -->

## Repo-Wide Static Analysis Evidence

<!-- Before user-facing completion, run full-repo static analysis. Preferred evidence is `make ci` because it includes pyright and ruff without quick-mode skips. If environment constraints prevent `make ci`, record full-repo `python3 -m pyright` and `python3 -m ruff check python tests --select D,E,F,I,UP` evidence and the toolchain repair performed. Do not unlock closeout with only `make ci-quick`. -->

## Spec-To-Product Coverage Evidence

<!-- For each must-do and completion-evidence clause, record the concrete product behavior, file, doc, test, command, or artifact that satisfies it. Do not unlock completion while any requested spec has no implemented product surface or explicit deferred/rejected clause. -->

## Review Finding Integration Evidence

<!-- Record every required review artifact and whether findings were fixed, escalated, or explicitly accepted as follow-up. Do not unlock completion while fix-now findings remain unapplied or unreviewed. -->

## Post-Fix Full Review Evidence

<!-- If any review-driven fix landed after an earlier review pass, record the refreshed full review artifact paths for the latest diff. If no post-review fixes occurred after the last full review pass, state that explicitly. -->

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

<!-- Record run-local subagent lifecycle evidence before user-facing completion. New user requests must use fresh subagents, not send_input to agents created for prior tasks. Stage-wave agents that are no longer needed must be closed before closeout. `reuse_for_new_task` records policy and must be `forbidden`; `previous_task_subagent_reuse` records observed compliance and must be `none`. This section is intentionally about run-local subagents; if a task is trivial and used no subagents, record close_agent_evidence as parent_direct_no_subagents plus the run-bundle reason. -->

- fresh_subagents_required:
- reuse_for_new_task:
- previous_task_subagent_reuse:
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

## Agent Evaluation Evidence

<!-- Run tools/agent_tools/evaluate_agent_run.py --report-dir <this-run> --behavior-manifest agents/evals/agent_behavior_eval.toml --write and record the resulting agent_evaluation.md status, score, feedback actions, and learning capture decision. Do not unlock completion while evaluation_status is not pass or feedback_actions_resolved is not yes. The evaluation must include workflow_monitoring.md evidence for active signals, Behavior Events, interventions, and skill/config/workflow/memory improvement decisions. -->

## Evidence

<!-- Record the exact verification artifact, review artifacts, commit, branch, and push evidence used to close the run. -->
