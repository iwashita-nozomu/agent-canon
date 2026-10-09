<!--
@dependency-start
contract data
responsibility Documents active AgentCanon eval definitions and accumulation.
upstream design ../../agents/canonical/skills.md skill canon registry
downstream implementation ../producers/evaluate_agent_run.py runs behavior evals
downstream implementation ../producers/generate_agent_improvement_guide.py summarizes observations without creating task obligations
downstream implementation ../checkers/eval_accumulation_check.py validates accumulated result evidence
downstream implementation ../producers/evaluate_workflow_selection.py runs workflow selection evals
downstream implementation ../producers/evaluate_codex_agent_roles.py runs Codex subagent role evals
@dependency-end
-->

# Eval Definitions

This directory stores eval definitions for observable run-bundle behavior,
workflow routing, and Codex role behavior.

Definitions, producers, checkers, and static fixtures are the eval source
contract. These manifests stay in `eval/definitions/`; runtime outputs do not.
All measurements, reports, packets, and logs are written to an explicit
external bootstrap runtime spool and, when retained, the separate
`agent-canon-log` archive (`<install-root-parent>/agent-canon-log/`).
[agents/evals/](../../agents/evals/README.md) documents legacy manifest-path resolution only.

## Reader Map

Use this README to answer which source-controlled eval manifests live under
`eval/definitions/`, which producer owns each eval family, and how closeout
uses behavior, workflow, and role evidence. Read the manifest table first, then the
extension order before adding a new eval domain. The closeout and protocol
sections explain how source manifests connect to accumulated runtime evidence
without storing run outputs here.

| Manifest or producer | Scope |
| --- | --- |
| `agent_behavior_eval.toml` | observable run-bundle behavior evidence. |
| `workflow_selection_eval.toml` | prompt-intake routing from user wording to workflow labels. |
| `evaluate_codex_agent_roles.py` | `.codex/agents/*.toml` role behavior, prohibitions, model / reasoning bucket, routing defaults, runtime metrics, and output-use evidence. |

Reader-facing report artifacts follow `report-writing` and
`result-artifact-writeout`; when selected, `report_reviewer` owns the report
review artifact.

Because the table fixes manifest ownership, the following commands are the
execution contract for those source manifests.

Because future evidence domains use the same registry, extend manifests in this
order:

1. Add more specific eval entries when an existing workflow, role, or observable
   behavior owner needs stronger evidence.
1. Declare accumulated eval result families in `eval_result_families.toml`.
1. Treat that registry as the abstract contract between eval producers, archive
   paths, filename / run-id checks, and consumers such as
   `eval_accumulation_check.py` and dashboards.
1. Keep the checker branch-free for future eval domains.
1. Add a registry family for structural analysis, writing-flow analysis,
   routing analysis, role behavior, deterministic responsibility, or other non-code
   evidence, then have the producer emit reports that satisfy the declared
   filename and run-id contract.

Use the bootstrap-owned collection route when selected validation requires
accumulated eval evidence. `eval collect` runs the registered producers and creates
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

## Behavior Eval Closeout Gate

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

Behavior evals inspect `workflow_monitoring.md`, `agent_evaluation.md`, review artifacts,
closeout evidence, and validation logs. `agent_behavior_eval.toml` and
[templates/agents/workflow_monitoring.md](../../templates/agents/workflow_monitoring.md) are the source packet for the
required behavior-event fields.

| Behavior event family | Required evidence |
| --- | --- |
| Skill and subagent routing | skill invocation, subagent routing, tool gates, and subagent lifecycle closeout. |
| Feedback resolution | structured user/reviewer feedback and static-analysis feedback when present. |
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

The archive boundary is documented in [documents/runtime/runtime-log-archive.md](../../documents/runtime/runtime-log-archive.md).
When a selected evaluation requires fresh archived results, use the bootstrap
collection and archive sync. Reading an existing guide does not activate them:

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval sync --run-id <run-id>
```

The collection command runs the registered role, skill/workflow prompt, and
workflow-selection evals; stdout/stderr and
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

## Improvement guide evidence

The [guide producer](../producers/generate_agent_improvement_guide.py) reads
existing private Issue references, knowledge, eval reports, and archived hook
observations. Its [workflow](../../.github/workflows/agent-improvement-guide.yml)
runs on its selected producer/test paths or manual dispatch, not ordinary PRs
or every branch push. It does not mutate those inputs or authorize a repair.

| Input | Interpretation |
| --- | --- |
| Candidate skills, workflows, and tools | Observed possibilities, not required selections. |
| Selected skills and human feedback | Separate counters; feedback does not establish a missed selection. |
| Failed eval reports and hook fingerprints | Evidence to inspect against the active contract before identifying the cause and repair owner. |
| Checker and failure targets | Affected inputs, not necessarily the code that caused the failure. |
| Missing or historical log fields | Observability limits until the producing contract establishes a violation. |

Candidate, feedback, and selection counts overlap and do not share a required
selection denominator. For example, one candidate, one feedback observation,
and one successful selection give `candidate + feedback - selected = 1`,
despite no established omission. This difference is not a routing-gap metric.
Keep the original counters rather than introducing another score or threshold;
repetition of a candidate alone must not create a repair obligation.

The guide preserves report paths, failure fingerprints, targets, counts, and
source cutover filtering for investigation. A failed report alone does not
identify a prompt defect, and absent evidence does not establish broken
instrumentation. Confirm the violated contract and concrete cause before
selecting an in-scope change under the existing owner. The guide does not require
protocol tokens, negative receipts, new checks, broad eval reruns, or skill edits.
Recording and validation remain with the already selected workflow and task;
reading this diagnostic report does not activate them.
