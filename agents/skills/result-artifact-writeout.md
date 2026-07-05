# result-artifact-writeout
<!--
@dependency-start
contract skill
responsibility Documents result-artifact-writeout for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../canonical/ARTIFACT_PLACEMENT.md run-local and durable artifact placement
upstream design ../../documents/experiment-report-style.md experiment report artifact policy
upstream design prose-reasoning-graph.md prose graph output artifact contract
downstream implementation ../../.agents/skills/result-artifact-writeout/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->


## Reader Map

- Purpose: explains how to preserve tool, hook, eval, experiment, review, and
  CI results as reusable artifacts instead of chat-only summaries.
- Use When: result saving, export, report generation, accumulated evals, or
  experiment evidence needs durable placement.
- Section path: Purpose and Use When define scope; Output Contract,
  Destination Rules, and Required Shape give the operational rules; Closeout
  Tokens names completion evidence.
- Boundary: generated reports are evidence artifacts, not policy truth.

## Purpose

tool、hook、eval、experiment、review、CI の結果を、あとから再利用できる
artifact として書き出すための skill です。
chat 要約だけで閉じず、raw result、human summary、manifest、report path を
同じ source result に結び付けます。

## Use When

- user が結果の保存、書き出し、export、report、表、JSON / JSONL / Markdown 化を求める
- tool / checker / hook / skill eval の結果を次の改善 branch が読む必要がある
- experiment result と reader-facing report を同じ run から作る
- prose graph projection、diagnostics、explanation、integration plan、rewrite packet を同じ source DB から書き出す
- 既存 result を上書きせず、unique ID 付きで蓄積したい

## Output Contract

- `source_result`: どの command、tool output、raw JSON / JSONL、run directory、hook line を正本にしたか
- `artifact_id`: timestamp、run id、hook_run_id、commit SHA、または run_name から作る unique ID
- `raw_artifact`: 生データまたは機械可読 result
- `summary_artifact`: Markdown / table / short report
- `manifest`: command、argv、cwd、branch、commit、runtime namespace、started / finished timestamp、exit code、status、input config、counts、schema version
- `destination_class`: `run-local`, `accumulated-eval`, `hook-result`, `experiment-result`, `reader-report`, `generated-triage`
- `overwrite_policy`: `append-only`, `unique-file`, `regenerate-from-source`, or explicit cleanup task

## Destination Rules

- run-local task evidence: `reports/agents/<run-id>/`
- normal cross-run agent report accumulation:
  `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/` on
  `logs/<environment-key>-<chat-key>`; discover exact paths with
  `python3 tools/agent_tools/runtime_log_archive_git.py status`
- archived agent report snapshot:
  `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/`
- accumulated skill / workflow eval: `.agent-canon/log-archive/eval-results/<eval-family>/<unique-id>.md`
- hook result chronology:
  `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>-<agent-canon-commit>.jsonl`
- experiment raw result: `experiments/<topic>/result/<run_name>/`; use
  `save-experiment-results` for retention plan, dirty-source formal-status,
  overwrite policy, and result branch evidence
- experiment reader report: `experiments/report/<run_name>.md`; use
  `save-experiment-results` when the report is tied to an experiment run
- managed experiment reproducibility artifacts:
  `run_manifest.json`, `eval_manifest.json`, `artifact_manifest.json`,
  `command.json`, `environment.json`, `source_snapshot.json`, `config.json`,
  `config_source.yaml`, `run.log`, `logs/startup.jsonl`, `logs/stdout.log`,
  and `logs/stderr.log` under the same `result/<run_name>/`
- formal experiment result branch: `experiment-results/<topic>` or the
  topic-specific branch fixed in the experiment plan. Route through
  `save-experiment-results` first, then publish with
  `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>`.
- generated triage report: `reports/<tool-or-task>/`

Do not store generated reports as policy truth. If a report changes a rule, edit
the canonical workflow, skill, document, or tool and cite the result artifact as
evidence.

## Required Shape

1. Choose the destination class before writing.
1. Preserve the raw machine-readable result before writing a prose summary.
1. If the user asks for a reader-facing report from tool, JSON / JSONL, hook,
   eval, checker, experiment, review, or audit evidence, also use
   `report-writing`. This skill owns raw / summary artifact writeout, not the
   report source packet, interpretation, limitations, next action, or quality
   checklist.
1. Derive tables and Markdown from the same raw result; do not rerun a checker
   just to get nicer prose unless the rerun is explicitly recorded as a new
   source result.
1. Treat failed, skipped, blocked, and partial runs as writeout targets too;
   do not drop them because they are not success evidence.
1. Use a unique path or append-only JSONL for repeated runs. Do not overwrite
   detailed eval, hook, skill, or experiment results.
1. When the active run-local agent report needs cross-run retention, call
   `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>`
   and then `python3 tools/agent_tools/runtime_log_archive_git.py push`. The snapshot records the run id,
   repo key, Codex trace key when exposed, and Git HEAD when available.
1. Use broad `python3 tools/agent_tools/runtime_log_archive_git.py sync` only
   when intentionally collecting accumulated runtime families such as hook
   JSONL, Codex runtime summaries, or all run-local agent reports.
1. Do not ask an agent to manually rewrite the report into the archive; the
   tool owns snapshot manifests and `index.jsonl`.
1. Include enough stable identifiers to group repeats without losing chronology:
   status, exit code, payload / input fingerprint, runtime namespace, branch,
   commit, and tool or hook name when available.
1. Include the artifact path in the final response or handoff.
1. If the result is reader-facing, separate observation, interpretation,
   limitations, and next action.
1. If multiple reader-facing formats are generated, such as Markdown and HTML,
   derive them from the same report content model or run a mechanical parity
   check. Do not allow a thin Markdown file that only points to the HTML report
   unless the task explicitly chooses HTML as the only reader-facing report.
1. For experiment reports where Markdown is the canonical reader report and
   HTML is a rendered artifact, the Markdown must contain the same substantive
   sections as HTML: method, summary table, item glossary, figure reading
   guides or backing data, comparison tables, case table, limitations, evidence
   trace, skill trace, report-quality eval, and artifact list.
1. Write reader-facing explanations, item glossary entries, figure/table
   reading guides, and report-quality eval descriptions in the repository's
   human-facing primary language unless the user asks otherwise; for this
   template root that means Japanese, while code identifiers and metric keys
   may remain literal.
1. If the report uses domain-specific item names, table columns, case IDs,
   metric names, abbreviations, or score labels, include an item glossary that
   defines each displayed item, unit, source artifact or measurement method,
   and how to interpret high/low or pass/fail values.
1. If the report includes figures or comparison tables, add a short reading
   guide for each one: axes or columns, units, whether higher/lower is better,
   the comparison baseline, and any metric-source caveat.
1. If the report includes a report-quality eval, make it strict and
   evidence-based: do not pass checks for mere section presence; require
   concrete glossary coverage, figure/table reading guides, source artifact
   traceability, metric-source caveats, limitations, and claim-to-artifact
   support. Missing required explanations, Markdown/HTML section parity, or
   Markdown standalone substance must fail the eval.

## Closeout Tokens

Record these in `reports/agents/<run-id>/workflow_monitoring.md`, a handoff, or the generated report:

```text
result_writeout=complete
result_source=<command-or-raw-artifact>
result_raw_artifact=<path>
result_summary_artifact=<path>
result_manifest=<path-or-inline>
result_overwrite_policy=<append-only|unique-file|regenerate-from-source>
```
