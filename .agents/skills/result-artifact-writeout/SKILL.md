---
name: result-artifact-writeout
description: Use when writing, exporting, saving, accumulating, or reporting tool/checker/hook/skill/eval/experiment results; creates durable raw and summary artifacts with unique IDs and no accidental overwrite.
---
<!--
@dependency-start
responsibility Documents Result Artifact Writeout for this repository.
upstream design ../../../agents/skills/result-artifact-writeout.md documents the human-facing skill
upstream design ../../../agents/canonical/ARTIFACT_PLACEMENT.md defines run-local and durable artifact placement
upstream design ../../../documents/experiment-report-style.md defines experiment report artifact policy
@dependency-end
-->


# Result Artifact Writeout

1. Read `agents/skills/result-artifact-writeout.md`.
1. Classify the destination before writing: `run-local`, `accumulated-eval`, `hook-result`, `experiment-result`, `reader-report`, or `generated-triage`.
1. Preserve the raw machine-readable source result first, then derive the Markdown/table summary from that same result.
1. Record `source_result`, `artifact_id`, raw artifact path, summary artifact path, manifest details, and overwrite policy; manifest details include command/argv, cwd, branch, commit, runtime namespace, timestamps, exit code, status, inputs, counts, and schema version when available.
1. Write failed, skipped, blocked, and partial runs too; they are routing evidence, not disposable noise.
1. Use append-only JSONL or a unique file path for repeated hook, skill eval, prompt eval, checker, or experiment runs; do not overwrite detailed results.
1. Include stable grouping fields such as payload/input fingerprint, hook/tool name, status, exit code, branch, commit, and runtime namespace when available.
1. For experiment outputs, keep raw run artifacts under `experiments/<topic>/result/<run_name>/` and reader-facing reports under `experiments/report/<run_name>.md`.
1. For run-local task evidence, write under `reports/agents/<run-id>/` and include the artifact path in the final response or handoff.
1. Separate observation, interpretation, limitations, and next action in reader-facing summaries.
1. Record closeout tokens: `result_writeout=complete`, `result_source=...`, `result_raw_artifact=...`, `result_summary_artifact=...`, `result_manifest=...`, and `result_overwrite_policy=...`.
