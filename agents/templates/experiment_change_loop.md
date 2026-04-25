# Experiment Change Loop
<!--
@dependency-start
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

## Goal

- Question: <!-- One sentence. -->
- Comparison Target: <!-- Baseline, main, external reference. -->
- Exit Criteria: <!-- What must be true before this loop can close? -->
- Stop Budget: <!-- Iteration count, runtime budget, or stop condition. -->
- Scope: <!-- Which files, experiment topics, and reports are in scope? -->

## Extension Backlog

| Backlog ID | Extension | Why Now | Expected Effect | Risk | Waterfall Run ID | Status |
| ---------- | --------- | ------- | --------------- | ---- | ---------------- | ------ |

## Fixed Protocol

- Baseline Ref: <!-- Commit, branch, or run directory. -->
- Metrics: <!-- Primary metrics and failure counts. -->
- Case Set: <!-- Dimensions, levels, dtypes, seeds, or dataset slice. -->
- Fairness Notes: <!-- Timeout, hardware, allocator, worker count, tuning rule. -->
- Artifact Paths: <!-- result/<run_name>/ and report path. -->

## Iterations

| Iteration | Backlog ID | Extension | Waterfall Run ID | Waterfall Gate Evidence | Validation | Run Name / Path | Critical Review | Report Review | Decision | Next Action |
| --------- | ---------- | --------- | ---------------- | ----------------------- | ---------- | --------------- | --------------- | ------------- | -------- | ----------- |

## Current State

- Active Extension ID: <!-- Backlog ID currently being executed. -->
- Active Waterfall Run ID: <!-- reports/agents/<run-id> for the current extension. -->
- Active Decision: <!-- report_rewrite_required / extra_validation_required / rerun_required / direction_rethink_required / approved / backlog_continue / stop_without_merge -->
- Best Current Evidence: <!-- Short factual summary only. -->
- Remaining Risk: <!-- What still blocks closure? -->

## Closeout Check

- Each iteration maps to exactly one backlog extension and one waterfall run id.
- The previous extension's waterfall pass is closed before the next extension starts.
- Latest baseline and changed runs use the same protocol.
- Quantitative summary is updated.
- Critical review outcome is recorded.
- Report review outcome is recorded.
- Next action or approved state is written.
