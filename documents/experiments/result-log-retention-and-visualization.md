<!--
@dependency-start
contract reference
responsibility Defines retention and visualization rules for result logs and reports.
upstream design ../conventions/coding-conventions-logging.md defines JSONL logging conventions
downstream design experiment-report-style.md defines human-readable experiment reports
upstream implementation ../../tools/data/jsonl_to_md.py converts JSONL to Markdown
upstream implementation ../../tools/hlo/summarize_hlo_jsonl.py summarizes HLO JSONL
downstream implementation ../../tools/docker_dependency_validator.sh validates runtime support
@dependency-end
-->

# Result Log Retention And Visualization

This document is the shared policy for result logs, run artifacts, summaries,
and visual outputs. It applies to agent runs, CI checks, experiments, benchmark
runs, and analysis tools.

This file owns storage classes and retention decisions. External runtime hook
JSONL and accumulated eval archive branch policy belong to
`documents/runtime/runtime-log-archive.md`.

## Reader Map

- Owns storage classes, bundle shape, visualization rules, retention rules, and
  closeout evidence for result logs and reports.
- Main path: Storage Classes, Required Bundle Shape, Visualization Rules,
  Retention Rules, and Closeout Evidence.
- Read this before deciding where run artifacts, summaries, images, notebooks,
  or report evidence should live.
- Boundary: external runtime hook JSONL and accumulated eval archive branch
  policy are owned by `documents/runtime/runtime-log-archive.md`.

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
  `documents/runtime/runtime-log-archive.md`.
- `experiments/<topic>/result/<variant>/<run-id>/` stores tracked compact
  review evidence: summaries, case records, manifests, small plots, and other
  material required to review the claim without annex access.
- `experiments/<topic>/result/<variant>/<run-id>/logs/` stores compact per-run
  diagnostics that are intentionally retained for review.
- `experiments/<topic>/raw/<variant>/<run-id>/` is the only source-side home for
  bulky raw outputs, traces, dumps, and large generated data. Its contents are
  ignored by Git through the topic-level `raw/.gitignore`.
- `experiments/<topic>/raw/<variant>/<run_name>.tar.gz` stores the one-run
  deterministic git-annex archive of that raw tree. The archive excludes
  `summary.json` and reader reports; its retention manifest binds the archive
  to tracked `summary.json` and `run_manifest.json` by repository path and SHA-256.
- `experiments/<topic>/visualize.ipynb` stores the Jupyter notebook used to visualize
  run artifacts and regenerate figures/tables from `result/<variant>/<run-id>/`.
- `experiments/report/<topic>/<variant>/<run-id>.md` stores the human-readable experiment report.
- `topic`, `variant`, and `run_name` form the immutable
  `agentcanon.experiment-run-identity/v2` nested identity in every manifest.
- `experiments/<topic>/result/<variant>/LATEST.json` and `LATEST.md` are the
  only latest-result pointers; they never compare or merge runs from another
  variant.
- Latest selection and the JSON/Markdown pair publication execute under one
  per-variant directory lock with a generation check. An explicit older run
  cannot overwrite a newer pointer, and a failed second replacement restores
  the first file so the pair is never left with mixed identities or temporary
  files.
- `tests/logs/[YYYYMMDD]-[HHMMSS]/` stores test-run raw logs, JSONL extracts,
  and exit-code records.

Do not use `reports/` as the raw-data home for topic-specific experiments.
Do not put raw experiment result trees directly under `documents/notes/`.

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
  `experiments/<topic>/visualize.ipynb` and read data from `result/<variant>/<run-id>/`.
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
python3 -m tools.experiments.save_experiment_result_annex --raw-dir experiments/<topic>/raw/<variant>/<run_name> --annex-repo "$EXPERIMENT_RAW_ANNEX_REPO"
python3 -m tools.experiments.update_latest_result experiments/<topic>/result --variant <variant>
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
- For formal experiments, commit the compact evidence under
  `experiments/<topic>/result/<variant>/<run_name>/`, then retain only
  `experiments/<topic>/raw/<variant>/<run_name>/` with
  `tools/experiments/save_experiment_result_annex.py` in the configured annex
  worktree. The append-only archive manifest records the tracked summary and run
  manifest path plus SHA-256; it has no compatibility route for whole-result
  archives and no remote-push mode.

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
