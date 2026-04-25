# User Request Contract
<!--
@dependency-start
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

## Gate Status

- all_clauses_resolved: no
- forbidden_drift_detected: no
- deferred_clause_ids:
- unresolved_clause_ids:

## Requirements Resolution Sweep

<!-- Record the accumulated context searched before leaving any open question: memory, notes/themes, notes/guardrails, notes/knowledge, notes/failures, documents, prior logs, local code, tests, and external constraints if needed. -->

## Resolved From Accumulated Context

| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |
| --------- | ------------- | ------------- | ---------- | -------------- |

## Must-Do Clauses

| Clause ID | Source Bucket | User Wording Or Evidence | Operational Interpretation | Owner Stage | Evidence Path | Status |
| --------- | ------------- | ------------------------- | -------------------------- | ----------- | ------------- | ------ |

## Must-Not-Do Clauses

| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |
| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |

## Completion Evidence Clauses

| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |
| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |

## Source Bucket Rules

- Allowed buckets: `current_request`, `durable_user_preference`, `repo_or_code_precedent`, `domain_or_external_constraint`, `unknown_or_open_question`.
- Durable user preferences do not become task requirements unless the current request or repo evidence supports the conversion.
- Unknowns stay unresolved, deferred, or escalated; they are not converted into silent assumptions.
- Active must-do, must-not-do, and completion-evidence clauses must not use `unknown_or_open_question`; unresolved items must move to Deferred Or Rejected Clauses after the resolution sweep.
- Do not stop at the first ambiguity if accumulated notes, repo docs, local code, tests, or prior logs can resolve it without changing user intent.

## Deferred Or Rejected Clauses

| Clause ID | Reason | Escalation Or Follow-Up Path | Status |
| --------- | ------ | ---------------------------- | ------ |

## Update Rule

- Every planning, design, implementation, and review artifact must cite the clause IDs it covers.
- If active work does not map to at least one must-do clause, stop and escalate instead of continuing.
- Closeout stays locked until every must-do and completion-evidence clause is resolved and every must-not-do clause remains clean.
