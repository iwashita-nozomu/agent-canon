# User Request Contract

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

## Gate Status

- all_clauses_resolved: no
- forbidden_drift_detected: no
- deferred_clause_ids:
- unresolved_clause_ids:

## Must-Do Clauses

| Clause ID | User Wording | Operational Interpretation | Owner Stage | Evidence Path | Status |
| --------- | ------------ | -------------------------- | ----------- | ------------- | ------ |

## Must-Not-Do Clauses

| Clause ID | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |
| --------- | --------------- | ------------------- | ----------- | ------------- | ------ |

## Completion Evidence Clauses

| Clause ID | Required Evidence | Where It Must Appear | Owner Stage | Status |
| --------- | ----------------- | -------------------- | ----------- | ------ |

## Deferred Or Rejected Clauses

| Clause ID | Reason | Escalation Or Follow-Up Path | Status |
| --------- | ------ | ---------------------------- | ------ |

## Update Rule

- Every planning, design, implementation, and review artifact must cite the clause IDs it covers.
- If active work does not map to at least one must-do clause, stop and escalate instead of continuing.
- Closeout stays locked until every must-do and completion-evidence clause is resolved and every must-not-do clause remains clean.
