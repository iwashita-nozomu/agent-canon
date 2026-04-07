# Experiment Change Loop

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

## Goal

- Question: <!-- One sentence. -->
- Comparison Target: <!-- Baseline, main, external reference. -->
- Exit Criteria: <!-- What must be true before this loop can close? -->
- Scope: <!-- Which files, experiment topics, and reports are in scope? -->

## Fixed Protocol

- Baseline Ref: <!-- Commit, branch, or run directory. -->
- Metrics: <!-- Primary metrics and failure counts. -->
- Case Set: <!-- Dimensions, levels, dtypes, seeds, or dataset slice. -->
- Fairness Notes: <!-- Timeout, hardware, allocator, worker count, tuning rule. -->
- Artifact Paths: <!-- result/<run_name>/ and report path. -->

## Iterations

| Iteration | Change | Validation | Run Name / Path | Critical Review | Report Review | Decision | Next Action |
| --------- | ------ | ---------- | --------------- | --------------- | ------------- | -------- | ----------- |

## Current State

- Active Decision: <!-- report_rewrite_required / extra_validation_required / rerun_required / approved -->
- Best Current Evidence: <!-- Short factual summary only. -->
- Remaining Risk: <!-- What still blocks closure? -->

## Closeout Check

- Latest baseline and changed runs use the same protocol.
- Quantitative summary is updated.
- Critical review outcome is recorded.
- Report review outcome is recorded.
- Next action or approved state is written.
