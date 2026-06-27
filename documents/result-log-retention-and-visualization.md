<!--
@dependency-start
contract reference
responsibility Defines retention and visualization rules for result logs and reports.
upstream design coding-conventions-logging.md defines JSONL logging conventions
downstream design experiment-report-style.md defines human-readable experiment reports
upstream implementation ../tools/data/jsonl_to_md.py converts JSONL to Markdown
upstream implementation ../tools/hlo/summarize_hlo_jsonl.py summarizes HLO JSONL
downstream implementation ../tools/docker_dependency_validator.sh validates runtime support
@dependency-end
-->

# Result Log Retention And Visualization

This document is the shared policy for result logs, run artifacts, summaries,
and visual outputs. It applies to agent runs, CI checks, experiments, benchmark
runs, and analysis tools.

This file owns storage classes and retention decisions. External runtime hook
JSONL and accumulated eval archive branch policy belong to
`documents/runtime-log-archive.md`.

## Reader Map

- Owns storage classes, bundle shape, visualization rules, retention rules, and
  closeout evidence for result logs and reports.
- Main path: Storage Classes, Required Bundle Shape, Visualization Rules,
  Retention Rules, and Closeout Evidence.
- Read this before deciding where run artifacts, summaries, images, notebooks,
  or report evidence should live.
- Boundary: external runtime hook JSONL and accumulated eval archive branch
  policy are owned by `documents/runtime-log-archive.md`.

## Storage Classes

- `reports/agents/<run-id>/` stores source-repo-local agent workflow evidence,
  reviews, validation, monitoring, and closeout material. `runtime_log_archive_git.py
  sync` copies those run bundles into the external log archive under
  `agent-reports/<repo-key>/<run-id>/` for accumulated retention.
- `reports/` stores repo-wide automation reports, dependency reviews, lint
  reports, merge audits, and other project-level checks.
- external runtime hook JSONL, accumulated eval reports, Codex runtime summaries,
  and archived agent run reports live under
  `.agent-canon/log-archive/...` as defined by
  `documents/runtime-log-archive.md`.
- `experiments/<topic>/result/<run-id>/` stores raw experiment outputs, JSONL,
  generated plots, HTML, SVG, HLO dumps, and machine-readable summaries.
- `experiments/<topic>/result/<run-id>/logs/` stores per-run stdout/stderr,
  tool, checker, and diagnostic logs that are not the managed wrapper `run.log`.
- `experiment-results/<topic>` or a topic-specific result branch stores the
  Git-retained copy of formal experiment result/report artifacts produced from
  the source checkout.
- `experiments/<topic>/visualize.ipynb` stores the Jupyter notebook used to visualize
  run artifacts and regenerate figures/tables from `result/<run-id>/`.
- `experiments/report/<run-id>.md` stores the human-readable experiment report.
- `tests/logs/[YYYYMMDD]-[HHMMSS]/` stores test-run raw logs, JSONL extracts,
  and exit-code records.

Do not use `reports/` as the raw-data home for topic-specific experiments.
Do not put raw experiment result trees directly under `notes/`.

## Required Bundle Shape

Every retained run directory should contain the smallest useful set below.

- `manifest.json`: run identity, command, commit, branch, host/runtime,
  start/end time, tool versions, and paths to raw outputs.
- `summary.json`: compact pass/fail, metrics, counts, and primary artifact paths.
- `events.jsonl`: one JSON object per event or measurement when event-level
  data is useful.
- `README.md` or `report.md`: short reader-facing entrypoint when the directory
  is not obvious from the parent report.

Long raw logs may be retained as `*.raw.txt`, but the closeout evidence must
point to a `summary.json`, `*.jsonl`, or reader-facing Markdown summary.

## Visualization Rules

- Prefer text-first summaries for closeout gates, then link plots or HTML.
- Store graph/plot outputs beside the data that generated them.
- For experiment visualization, keep the Jupyter notebook at
  `experiments/<topic>/visualize.ipynb` and read data from `result/<run-id>/`.
  Do not use notebooks as the formal run launcher or config source of truth.
- Use deterministic formats (`svg`, `png`, `html`, `json`) and record the
  generation command in the manifest.
- For dependency and structural graphs, keep the source edges or DOT input with
  the rendered artifact.
- For HLO or compiler dumps, keep a compact JSON summary beside the raw dump.

Canonical helper commands:

```bash
python3 tools/data/jsonl_to_md.py <input.jsonl> <output.md>
python3 tools/hlo/summarize_hlo_jsonl.py <hlo.jsonl> > summary.json
python3 tools/experiments/html_artifact_access.py <report.html>
python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>
dot -V
```

When an HTML report is produced on an SSH-reached HPC host or inside a container
on that host, use `tools/experiments/html_artifact_access.py` to record the
`python3 -m http.server` command, SSH tunnel command, and local browser URL. The
default bind address is `127.0.0.1`; use `--use-container-ip` when serving
directly from inside a container and tunneling to the container IP.

## Retention Rules

- Keep source-of-truth reports and summaries in tracked paths only when they are
  durable project knowledge or release evidence.
- Keep bulky raw run outputs untracked unless the task explicitly requires
  publishing them.
- Generated `reports/broken_links.txt`, transient Docker build logs, pycache,
  and local notebook checkpoints are cleanup targets before closeout.
- If a generated artifact is needed for review but should not be tracked, put
  its path and checksum in `verification.txt` or the experiment report.
- If a run-local `reports/agents/<run-id>/` bundle is needed after the current
  task, archive it mechanically with `runtime_log_archive_git.py
  archive-agent-report`; do not create a hand-written duplicate report in the
  source tree.
- For formal experiments, run from the source checkout and publish the generated
  `experiments/<topic>/result/<run_name>/` plus
  `experiments/report/<run_name>.md` with
  `tools/experiments/publish_result_branch.py`. Use `--push` when the retention
  decision is remote result-branch storage.

## Closeout Evidence

Before user-facing completion, record:

- command used to create the run/log artifact;
- raw output path;
- summary/report path;
- visualization path if one exists;
- retention decision: `tracked`, `ignored`, `external`, or `deleted-after-use`;
- reviewer or mechanical gate that consumed the artifact.

If the artifact is deleted after use, the closeout artifact must retain enough
summary evidence to support the final claim.
