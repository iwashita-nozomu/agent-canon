<!--
@dependency-start
contract data
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../../agents/canonical/skills.md skill canon registry
downstream implementation ../producers/evaluate_skill_workflow_prompts.py runs these evals
downstream implementation ../producers/evaluate_agent_run.py runs behavior evals
downstream implementation ../checkers/eval_accumulation_check.py validates accumulated result evidence
downstream implementation ../producers/evaluate_workflow_selection.py runs workflow selection evals
downstream implementation ../producers/evaluate_report_quality.py runs report quality evals
downstream implementation ../producers/evaluate_codex_agent_roles.py runs Codex subagent role evals
@dependency-end
-->

# Skill And Workflow Prompt Evals

This directory stores deterministic eval definitions for agent-facing skills, workflows, and
run-bundle behavior evidence.
Prompt evals are frozen checklists for one prompt surface or one glob-expanded prompt family.
Behavior evals are frozen criteria for observable agent actions recorded in run artifacts.

Definitions, producers, checkers, and static fixtures are the eval source
contract. These manifests stay in `eval/definitions/`; runtime outputs do not.
All measurements, reports, packets, and logs are written to an explicit
external bootstrap runtime spool and, when retained, the separate
`agent-canon-log` archive (`<install-root-parent>/agent-canon-log/`).
`agents/evals/` remains only a legacy path resolver.

## Reader Map

Use this README to answer which source-controlled eval manifests live under
`eval/definitions/`, which producer owns each eval family, and how closeout
uses prompt and behavior eval evidence. Read the manifest table first, then the
extension order before adding a new eval domain. The closeout and protocol
sections explain how source manifests connect to accumulated runtime evidence
without storing run outputs here.

| Manifest or producer | Scope |
| --- | --- |
| `skill_workflow_prompt_eval.toml` | all discoverable skill shims, human-facing skill docs, and workflow docs. |
| `agent_behavior_eval.toml` | observable run-bundle behavior evidence. |
| `workflow_selection_eval.toml` | prompt-intake routing from user wording to workflow labels. |
| `report_quality_eval.toml` | report-writing checklist, artifact separation, and reviewer routing. |
| `evaluate_codex_agent_roles.py` | `.codex/agents/*.toml` role behavior, prohibitions, model / reasoning bucket, routing defaults, runtime metrics, and output-use evidence. |

Because the table fixes manifest ownership, the following commands are the
execution contract for those source manifests.

Because future evidence domains use the same registry, extend manifests in this
order:

1. Add more specific eval entries when a specific skill, workflow, role, or report
   surface needs stronger invariants.
1. Declare accumulated eval result families in `eval_result_families.toml`.
1. Treat that registry as the abstract contract between eval producers, archive
   paths, filename / run-id checks, and consumers such as
   `eval_accumulation_check.py` and dashboards.
1. Keep the checker branch-free for future eval domains.
1. Add a registry family for structural analysis, writing-flow analysis,
   routing analysis, role behavior, deterministic responsibility, or other non-code
   evidence, then have the producer emit reports that satisfy the declared
   filename and run-id contract.

Use the bootstrap-owned collection route when changing a skill, workflow, or
routing prompt. `eval collect` runs the registered producers and creates
`collection.json` in the runtime spool; `eval sync` publishes that collection
to the external `agent-canon-log` archive:

```bash
BOOTSTRAP=<agent-canon-source>/bootstrap.sh
ROOT=<authorized-parent-root>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

The collection and sync commands are the canonical user flow. Agent-facing eval
runs write bounded statistics and `collection.json` before the agent reads
details:

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
```

When a run uses skills, run the same prompt eval with accumulated evidence.
Detailed reports are tool-written, not agent-authored prose. They are first
written to the explicit runtime spool and then published to the external
`agent-canon-log` archive; they are never written to this source checkout or
overwritten during normal agent work:

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

The file name convention is:

```text
<eval_run_id>-<status>-<skill-slug>.md
```

| Accumulated prompt eval field | Contract |
| --- | --- |
| `eval_run_id` | assigned by the tool as `skill-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>`. |
| `EVAL_RUN_ID=<eval_run_id>` | machine-readable run identity. |
| `EVAL_USED_SKILLS=<comma-separated-skills>` | machine-readable skill-use evidence. |
| `EVAL_ACCUMULATED_REPORT=<path>` | machine-readable accumulated report path. |
| Run-bundle behavior path | must exist, must not be a placeholder, and must contain the matching eval run id. |
| Existing `--report-out` path | writes a sibling path with the same `eval_run_id` appended instead of overwriting it. |

## Prompt Eval Closeout Order

1. Require every critical checklist item to pass.
1. Require the manifest audit to pass.
1. Treat duplicate eval IDs, duplicate explicit targets, and duplicate checklist IDs within an eval as fail-closed audit findings.
1. Keep `EVAL_AUDIT_STATUS=pass` and `EVAL_GROWTH_CANDIDATES=0` before closing
   skill or workflow prompt improvement work.
1. When a prompt surface needs additional coverage, add checklist items to the
   existing eval entry for that target instead of adding a second
   explicit-target eval.
1. If an eval reports drift, fix the target prompt and rerun the same manifest
   until the report passes.

## Behavior Eval Closeout Gate

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

Behavior evals inspect `workflow_monitoring.md`, `agent_evaluation.md`, review artifacts,
closeout evidence, and validation logs. `agent_behavior_eval.toml` and
`templates/agents/workflow_monitoring.md` are the source packet for the
required behavior-event fields.

| Behavior event family | Required evidence |
| --- | --- |
| Skill and subagent routing | skill invocation, subagent routing, tool gates, and subagent lifecycle closeout. |
| Prompt and feedback resolution | accumulated prompt eval runs, feedback resolution, static-analysis feedback, and diff-check decisions. |
| Code checker results | `tool_call=pyright code_checker=pass`, `tool_call=ruff code_checker=pass`, `tool_call=oop-readability-check code_checker=pass`, or `code_checker_not_required`. |
| Run comparison | execution path comparison and token footprint comparison when the task makes those comparisons relevant. |

New behavior-event rows use the namespaced `agent-canon.behavior-event.v1`
schema. `eval_accumulation_check.py` validates the bounded fields structurally:
`workflow_attribution_kind` is `owner`, `context`, or `missing` with matching
owner/context lists, and `prompt_capture_status` is `present` or `missing` with
coherent redacted excerpt, fingerprint, character-count, and truncation fields.
Legacy behavior-shaped rows remain readable as non-blocking migration warnings;
they are not promoted to canonical evidence.

## Protocol Feedback Boundary

| Protocol boundary | Required record |
| --- | --- |
| Hook/tool review | `hook_tool_feedback=reviewed` and `protocol_feedback_reason=...`. |
| Parent update | `parent_protocol_update=<applied|recorded|not_required>`. |
| Subagent update | `subagent_protocol_update=<applied|recorded|not_required>`. |
| Archive identity | unique `hook_run_id` values under the external `agent-canon-log` archive's `hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl`. |
| Legacy source-tree result path | `agents/evals/results/` is not a normal read or write location; old results must be imported into the external archive and deleted from source. |

The archive boundary is documented in `documents/runtime/runtime-log-archive.md`.
Run the bootstrap collection and archive sync before using accumulated evidence
in a PR or guide:

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

The collection command runs the registered role, skill/workflow prompt,
workflow-selection, and report-quality evals; stdout/stderr and
`collection.json` go to the explicit `<install-root>/.runtime/spool/<run-id>/`
path. The sync command is the only archive publication step. Agents do not
hand-generate these reports. The gate validates directory mounted JSONL readability when available,
every family declared in `eval_result_families.toml`, unique run ids,
non-ignored tracked evidence paths, and intentionally ignored archive paths,
without compacting or deleting archive results.

Specialized evals share the same source/result boundary: definitions, producers,
checkers, and fixtures live under `eval/`; accumulated reports and logs live in
the external runtime spool and `agent-canon-log` archive.
The checked-in shim measurement fixture is a static source fixture at
`eval/fixtures/skill-runtime-shim/measurements/fixture-measurement.json`;
generated measurements are external runtime artifacts. Runtime spool copies
are transient producer output and are not an alternate oracle.

| Eval surface | Command | Accumulated evidence and privacy rule |
| --- | --- | --- |
| Workflow selection | included in `bootstrap.sh ... eval collect --root <project-root> --run-id <run-id>` | reports list case IDs, expected workflow labels, and observed workflow labels; they do not store raw prompt text. |
| Report quality | included in `bootstrap.sh ... eval collect --root <project-root> --run-id <run-id>` | reports list checklist IDs and missing patterns; they do not store raw report drafts or prompts. |
| Codex subagent roles | included in `bootstrap.sh ... eval collect --root <project-root> --run-id <run-id>` | accumulated reports use `codex-agent-role-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>-<status>.md` and record `CODEX_AGENT_ROLE_EVAL_RUN_ID=<eval_run_id>`. |

`workflow_selection_eval.toml` may define reusable `[[case_groups]]`.
Each group supplies prompt templates, subjects, expected workflow labels, and
optional expected skill / tool labels. The workflow-selection producer expands
those groups before evaluation and fails closed when `expected_case_count` or
`expected_generated_case_count` does not match the expanded corpus. The
canonical manifest intentionally expands to 500 realistic user-task prompts
across 20 route families, while reports preserve only case IDs, route labels,
skills, tools, count checks, and the optional source `--run-id`.

The role eval fails when a role TOML violates this contract:

| Role eval concern | Contract |
| --- | --- |
| Registration | every role TOML is registered. |
| Cost bucket | model and reasoning bucket are not over-costed for the role. |
| Prohibitions | read-only and findings-first prohibitions are present where required. |
| Routing order | broad reviewers are not routed before boundary-relevant language or diff-triage reviewers. |
| Runtime metrics | optional `--runtime-log <path>` uses bounded fields such as `agent`, `tokens`, `latency_ms`, `retry_count`, `parent_intervention`, `format_violation`, and `output_used`. |
| Missing metrics | `ROLE_RUNTIME_METRICS_STATUS=missing` is reported without failing the eval. |

Because GitHub Actions consumes the same archived hook results, memory notes,
skill eval reports, and `issues/open|closed/`, it generates a read-only
Agent Improvement Guide on PRs and branch pushes.

| Improvement-guide input | Required summary boundary |
| --- | --- |
| Prompt routing | candidate skill / workflow / tool routing inferred from prompts, without unbounded raw prompt text. |
| Human feedback | human feedback labels and targets plus explicit human feedback labels. |
| Skill and hook coverage | skill usage entries, skill/event coverage, hook source files, hook tool names, and hook-quality counters. |
| Code and run evidence | code-checker target paths, repeated failure fingerprints, and `workflow_monitoring.md` tokens from run comparison tools. |
| Token reduction | compare Codex session footprints only when token reduction is selected as the objective; otherwise record `token_efficiency_not_required`. |

| Run evidence concern | Required action |
| --- | --- |
| Prompt privacy | store bounded, redacted prompt excerpts, fingerprints, and counts instead of transcript text. |
| Alternative paths | compare runs with `eval/checkers/compare_agent_run_paths.py` and record `execution_path_comparison`, `route_efficiency`, `selected_inefficient_route`, and `static_analysis_feedback`. |
| Token reduction | compare footprints with `eval/checkers/compare_codex_token_footprints.py` when token reduction is part of the objective. No global count, ratio, or improvement threshold is required. |
| During-run recording | Record these events during the run with `tools/runtime/lifecycle/workflow_monitor.py --behavior-event "..."` instead of reconstructing them only at closeout. |
