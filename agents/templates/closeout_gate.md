# Closeout Gate

<!--
@dependency-start
upstream design ../canonical/CODEX_WORKFLOW.md closeout workflow contract
upstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
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
- spec_product_coverage_complete: no
- review_findings_integrated: no
- post_fix_full_review_complete: no
- canonical_tree_head_complete: no
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
- spec_product_coverage_complete: yes
- review_findings_integrated: yes
- post_fix_full_review_complete: yes
- canonical_tree_head_complete: yes
- commit_created: yes
- push_completed: yes

## Completion Boundary Evidence

<!-- Record why this is the whole user-request completion, not just a chunk, slice, checkpoint, or subpass completion. List all planned work units and active clauses as complete, confirm schedule.md remains the TODO source of truth, confirm no unfinished task / follow-up / validation / commit / push / canon-sync item remains in scope, and explain why closeout stays locked if work_log.md or TODO coverage is incomplete. -->

## Dependency Manifest Evidence

<!-- Confirm that every created or edited human-authored text file has a top-of-file @dependency-start / @dependency-end manifest block, or record the scan-tool classification reason and alternate manifest/design artifact for files that cannot carry such a block. Include output from check_dependency_headers.py, scan_dependency_headers.sh, check_dependency_header_format.sh, and check_dependency_graph.sh when dependency edges changed. During migration, record any pre-existing full-repo graph baseline separately and confirm this change introduced no new old-format header, self reference, reverse-edge gap, kind mismatch, or cycle. -->

## Spec-To-Product Coverage Evidence

<!-- For each must-do and completion-evidence clause, record the concrete product behavior, file, doc, test, command, or artifact that satisfies it. Do not unlock completion while any requested spec has no implemented product surface or explicit deferred/rejected clause. -->

## Review Finding Integration Evidence

<!-- Record every required review artifact and whether findings were fixed, escalated, or explicitly accepted as follow-up. Do not unlock completion while fix-now findings remain unapplied or unreviewed. -->

## Post-Fix Full Review Evidence

<!-- If any review-driven fix landed after an earlier review pass, record the refreshed full review artifact paths for the latest diff. If no post-review fixes occurred after the last full review pass, state that explicitly. -->

## Canonical Tree-Head Evidence

<!-- Record the canonical design-document paths and implementation paths left in the tracked tree, and state which non-canonical drafts, copied implementations, snapshots, mirrored directories, or backup files were deleted or confirmed absent. Do not unlock completion while the tree carries more than one durable truth surface. -->

## Evidence

<!-- Record the exact verification artifact, review artifacts, commit, branch, and push evidence used to close the run. -->
