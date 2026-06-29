<!--
@dependency-start
contract data
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../../agents/canonical/skills.md skill canon registry
downstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py runs these evals
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py runs behavior evals
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated result evidence
downstream implementation ../../rust/agent-canon/src/local_llm.rs routes local LLM eval commands
downstream implementation ../../tools/agent_tools/local_llm_eval.py runs local LLM responsibility evals
downstream implementation ../../tools/agent_tools/evaluate_workflow_selection.py runs workflow selection evals
downstream implementation ../../tools/agent_tools/evaluate_report_quality.py runs report quality evals
downstream implementation ../../tools/agent_tools/evaluate_codex_agent_roles.py runs Codex subagent role evals
@dependency-end
-->

# Skill And Workflow Prompt Evals

This directory stores deterministic eval definitions for agent-facing skills, workflows, and
run-bundle behavior evidence.
Prompt evals are frozen checklists for one prompt surface or one glob-expanded prompt family.
Behavior evals are frozen criteria for observable agent actions recorded in run artifacts.

These manifests must stay in `evidence/agent-evals/` because the dependency
header makes this directory the source-controlled evidence contract. Runtime
outputs stay in the mounted archive, and `agents/evals/` remains only a legacy
path resolver.

## Reader Map

Use this README to answer which source-controlled eval manifests live under
`evidence/agent-evals/`, which producer owns each eval family, and how closeout
uses prompt and behavior eval evidence. Read the manifest table first, then the
extension order before adding a new eval domain. The closeout and protocol
sections explain how source manifests connect to accumulated runtime evidence
without storing run outputs here.

| Manifest or producer | Scope |
| --- | --- |
| `skill_workflow_prompt_eval.toml` | all discoverable skill shims, human-facing skill docs, and workflow docs. |
| `agent_behavior_eval.toml` | observable run-bundle behavior evidence. |
| `local_llm_responsibility_eval.toml` | single-file advisory responsibility analysis. |
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
   routing analysis, role behavior, local-LLM responsibility, or other non-code
   evidence, then have the producer emit reports that satisfy the declared
   filename and run-id contract.

Use these evals when changing a skill, workflow, or routing prompt:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml
```

Agent-facing eval runs should write bounded statistics before the agent reads
details:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml \
  --compact-out reports/agents/<run-id>/skill-workflow-prompt-compact.json
```

When a run uses skills, run the same prompt eval with accumulated evidence.
Detailed reports are tool-written, not agent-authored prose, and are stored in
the mounted runtime log archive under
`.agent-canon/log-archive/eval-results/skill-workflow-prompt/` and are never
overwritten during normal agent work:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml \
  --accumulate \
  --run-id <run-id> \
  --skill-used agent-orchestration
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
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml \
  --write
```

Behavior evals inspect `workflow_monitoring.md`, `agent_evaluation.md`, review artifacts,
closeout evidence, and validation logs. `agent_behavior_eval.toml` and
`agents/templates/workflow_monitoring.md` are the source packet for the
required behavior-event fields.

| Behavior event family | Required evidence |
| --- | --- |
| Skill and subagent routing | skill invocation, subagent routing, tool gates, and subagent lifecycle closeout. |
| Prompt and feedback resolution | accumulated prompt eval runs, feedback resolution, static-analysis feedback, and diff-check decisions. |
| Code checker results | `tool_call=pyright code_checker=pass`, `tool_call=ruff code_checker=pass`, `tool_call=oop-readability-check code_checker=pass`, or `code_checker_not_required`. |
| Run comparison | execution path comparison and token footprint comparison when the task makes those comparisons relevant. |

## Protocol Feedback Boundary

| Protocol boundary | Required record |
| --- | --- |
| Hook/tool review | `hook_tool_feedback=reviewed` and `protocol_feedback_reason=...`. |
| Parent update | `parent_protocol_update=<applied|recorded|not_required>`. |
| Subagent update | `subagent_protocol_update=<applied|recorded|not_required>`. |
| Archive identity | unique `hook_run_id` values under `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl`. |
| Legacy source-tree result path | `agents/evals/results/` is not a normal read or write location; old results must be imported into the archive and deleted from source. |

The archive boundary is documented in `documents/runtime-log-archive.md`.
Run the mechanical producer before using accumulated evidence in a PR or guide:

```bash
python3 tools/agent_tools/run_accumulated_agent_evals.py \
  --root . \
  --run-id <run-id>
python3 tools/agent_tools/eval_accumulation_check.py --root .
```

The producer runs the registered role, skill/workflow prompt, local LLM,
workflow-selection, and report-quality evals with `--accumulate`; stdout/stderr
go to `reports/agent-eval-runs/<run-id>/`. Agents do not hand-generate these
reports. The gate validates directory mounted JSONL readability when available,
every family declared in `eval_result_families.toml`, unique run ids,
non-ignored tracked evidence paths, and intentionally ignored archive paths,
without compacting or deleting archive results.

Specialized evals share the same source/result boundary: source manifests live
in this directory, accumulated reports live under `.agent-canon/log-archive/`,
and bounded run stdout/stderr may live under `reports/agent-eval-runs/<run-id>/`.

| Eval surface | Command | Accumulated evidence and privacy rule |
| --- | --- | --- |
| Local LLM responsibility | `agent-canon local-llm eval --manifest evidence/agent-evals/local_llm_responsibility_eval.toml` | `--accumulate` writes `.agent-canon/log-archive/eval-results/local-llm-responsibility/`; `--run-llm` is optional and intentional. |
| Workflow selection | `python3 tools/agent_tools/evaluate_workflow_selection.py --manifest evidence/agent-evals/workflow_selection_eval.toml` | reports list case IDs, expected workflow labels, and observed workflow labels; they do not store raw prompt text. |
| Report quality | `python3 tools/agent_tools/evaluate_report_quality.py --manifest evidence/agent-evals/report_quality_eval.toml` | reports list checklist IDs and missing patterns; they do not store raw report drafts or prompts. |
| Codex subagent roles | `python3 tools/agent_tools/evaluate_codex_agent_roles.py` | accumulated reports use `codex-agent-role-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>-<status>.md` and record `CODEX_AGENT_ROLE_EVAL_RUN_ID=<eval_run_id>`. |

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
| Token reduction | compare Codex session footprints when token reduction is part of the objective; otherwise record `token_efficiency_not_required`. |

| Run evidence concern | Required action |
| --- | --- |
| Prompt privacy | store bounded, redacted prompt excerpts, fingerprints, and counts instead of transcript text. |
| Alternative paths | compare runs with `tools/agent_tools/compare_agent_run_paths.py` and record `execution_path_comparison`, `route_efficiency`, `selected_inefficient_route`, and `static_analysis_feedback`. |
| Token reduction | compare footprints with `tools/agent_tools/compare_codex_token_footprints.py` when token reduction is part of the objective. |
| During-run recording | Record these events during the run with `tools/agent_tools/workflow_monitor.py --behavior-event "..."` instead of reconstructing them only at closeout. |
