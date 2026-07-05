---
name: result-artifact-writeout
description: Use when writing, exporting, saving, accumulating, or reporting tool/checker/hook/skill/eval/experiment results; creates durable raw and summary artifacts with unique IDs and no accidental overwrite.
---
<!--
@dependency-start
contract skill
responsibility Documents Result Artifact Writeout for this repository.
upstream design ../../../agents/skills/result-artifact-writeout.md documents the human-facing skill
upstream design ../../../agents/canonical/ARTIFACT_PLACEMENT.md defines run-local and durable artifact placement
upstream design ../../../documents/experiment-report-style.md defines experiment report artifact policy
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph output artifacts
@dependency-end
-->


# Result Artifact Writeout

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill result-artifact-writeout --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/result-artifact-writeout.md`.
1. Classify the destination before writing: `run-local`, `accumulated-eval`, `hook-result`, `experiment-result`, `reader-report`, or `generated-triage`.
1. Preserve the raw machine-readable source result first, then derive the Markdown/table summary from that same result.
1. For prose graph outputs, treat the SQLite DB as the source result and keep projection, diagnostics, explanation, integration plan, handoff, and rewrite packets tied to that DB path.
1. If the user asks for a reader-facing report from tool, JSON/JSONL, hook, eval, checker, experiment, review, or audit evidence, also use `$report-writing`; this skill owns raw/summary artifact writeout, not the report source packet, interpretation, limitations, next action, or quality checklist.
1. Record `source_result`, `artifact_id`, raw artifact path, summary artifact path, manifest details, and overwrite policy; manifest details include command/argv, cwd, branch, commit, runtime namespace, timestamps, exit code, status, inputs, counts, and schema version when available.
1. Write failed, skipped, blocked, and partial runs too; they are routing evidence, not disposable noise.
1. Use append-only JSONL or a unique file path for repeated hook, skill eval, prompt eval, checker, or experiment runs; do not overwrite detailed results.
1. Include stable grouping fields such as payload/input fingerprint, hook/tool name, status, exit code, branch, commit, and runtime namespace when available.
1. For experiment outputs, use `$save-experiment-results` with this skill. Keep raw run artifacts under `experiments/<topic>/result/<run_name>/` and reader-facing reports under `experiments/report/<run_name>.md`. Raw run artifacts include `run_manifest.json`, `eval_manifest.json`, `artifact_manifest.json`, `command.json`, `environment.json`, `source_snapshot.json`, `config.json`, `config_source.yaml`, `run.log`, `logs/startup.jsonl`, `logs/stdout.log`, and `logs/stderr.log`.
1. For formal experiment retention, `$save-experiment-results` owns the retention plan, dirty-source formal-status, overwrite policy, and result branch evidence before publishing raw/report artifacts with `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>`; add `--push` when the retention plan includes remote storage.
1. For run-local task evidence, write under `reports/agents/<run-id>/` and include the artifact path in the final response or handoff.
1. To find the exact report placement for the current repo, run `python3 tools/agent_tools/runtime_log_archive_git.py status` and read `RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL`, `RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH`, and `RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR`.
1. For normal cross-run retention of run-local agent reports, do not hand-generate an archive report. Use `python3 tools/agent_tools/runtime_log_archive_git.py sync`; it copies `reports/agents/` into `.agent-canon/log-archive/agent-reports/<repo-key>/` on `logs/<repo-key>`.
1. For an immutable publication snapshot of one run bundle, use `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>` followed by `python3 tools/agent_tools/runtime_log_archive_git.py push`; the tool writes `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/`, `archive_manifest.json`, and `index.jsonl`.
1. Separate observation, interpretation, limitations, and next action in reader-facing summaries.
1. If multiple reader-facing formats are generated, such as Markdown and HTML, derive them from the same report content model or run a mechanical parity check; do not allow a thin Markdown file that only points to HTML unless the task explicitly chooses HTML as the only reader-facing report.
1. For experiment reports where Markdown is the canonical reader report and HTML is a rendered artifact, the Markdown must contain the same substantive sections as HTML: method, summary table, item glossary, figure reading guides or backing data, comparison tables, case table, limitations, evidence trace, skill trace, report-quality eval, and artifact list.
1. Write reader-facing explanations, item glossary entries, figure/table reading guides, and report-quality eval descriptions in the repository's human-facing primary language unless the user asks otherwise; in this template root, use Japanese while leaving code identifiers and metric keys literal.
1. For reader-facing reports with domain-specific item names, table columns, case IDs, metric names, abbreviations, or score labels, include an item glossary that defines each displayed item, unit, source artifact or measurement method, and high/low or pass/fail interpretation.
1. For reader-facing figures or comparison tables, include a concise reading guide for each one: axes or columns, units, whether higher/lower is better, the comparison baseline, and any metric-source caveat.
1. For report-quality evals, use strict evidence-based checks: mere section presence is not enough; missing item glossary coverage, reading guides, source artifact traceability, metric-source caveats, limitations, claim-to-artifact support, Markdown/HTML section parity, or Markdown standalone substance must fail the eval.
1. Record closeout tokens: `result_writeout=complete`, `result_source=...`, `result_raw_artifact=...`, `result_summary_artifact=...`, `result_manifest=...`, and `result_overwrite_policy=...`.
