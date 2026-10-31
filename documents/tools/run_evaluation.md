# Evaluate Agent Run

`agent-canon run-evaluation` scores one run bundle and optionally writes its
`agent_evaluation.md` report through the external runtime artifact boundary.

## Command

```text
tools/bin/agent-canon run-evaluation (--run-id <run-id> | --report-dir <path>)
  [--report-root <path>] [--workspace-root <path>]
  [--behavior-manifest <path>] [--min-score <score>]
  [--output <path>] [--runtime-root <path>] [--write]
```

`--run-id` resolves below the external `reports/agents` runtime directory.
`--report-dir` selects an explicit run directory. `--workspace-root` defaults to
the current directory and owns behavior-manifest resolution. Legacy manifest
paths under `agents/evals/` resolve to `eval/definitions/` with a deprecation
warning that identifies the Rust call site.

`--write` atomically writes the report beneath an explicit `--runtime-root` or
the configured `AGENT_CANON_RUNTIME_ROOT`. Without `--write`, the evaluator
prints status and score lines without creating the report.

## Artifact selection and scoring

The evaluator reads selected required outputs from
`team_manifest.yaml` `roles[].required_outputs`. Its `artifacts` list records
materialized files. A required output missing from either source or disk fails
the fixed 8-point artifact-completeness criterion. An absent or invalid
selection record is a revise blocker because requiredness is unknown.

The fixed 10-point planning criterion checks `schedule.md` and `work_log.md`
only when selected. A run selecting neither receives 10 points for this
criterion; other criteria still run. Missing or invalid selected files receive
0/10. Present schedules require content under the stage-plan, clause-coverage, and
planned-work-unit sections plus at least one planned-work-unit table row. Present
work logs require a nonempty `## Entries` section with at least one bullet row.

The evaluator also checks request traceability, monitoring, tool warnings,
orchestration intake, review, closeout, dependency evidence, retrospective
feedback, validation-failure evidence, and manifest-defined behavior criteria.
