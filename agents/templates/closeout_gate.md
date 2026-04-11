# Closeout Gate

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
- spec_product_coverage_complete: no
- review_findings_integrated: no
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
- spec_product_coverage_complete: yes
- review_findings_integrated: yes
- commit_created: yes
- push_completed: yes

## Completion Boundary Evidence

<!-- Record why this is the whole user-request completion, not just a chunk, slice, checkpoint, or subpass completion. List all planned work units and active clauses as complete, confirm schedule.md remains the TODO source of truth, and explain why closeout stays locked if work_log.md or TODO coverage is incomplete. -->

## Spec-To-Product Coverage Evidence

<!-- For each must-do and completion-evidence clause, record the concrete product behavior, file, doc, test, command, or artifact that satisfies it. Do not unlock completion while any requested spec has no implemented product surface or explicit deferred/rejected clause. -->

## Review Finding Integration Evidence

<!-- Record every required review artifact and whether findings were fixed, escalated, or explicitly accepted as follow-up. Do not unlock completion while fix-now findings remain unapplied or unreviewed. -->

## Evidence

<!-- Record the exact verification artifact, review artifacts, commit, branch, and push evidence used to close the run. -->
