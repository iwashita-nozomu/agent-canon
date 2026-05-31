<!--
@dependency-start
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../canonical/skills.md skill canon registry
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
The default prompt manifest covers all discoverable skill shims, all human-facing skill docs,
and all workflow docs. Add narrower eval entries when a specific skill or workflow needs
stronger invariants.
Local LLM responsibility evals live in `local_llm_responsibility_eval.toml` and
only cover single-file advisory responsibility analysis.
Workflow selection evals live in `workflow_selection_eval.toml` and cover the
prompt-intake route from user wording to candidate workflow labels.
Report quality evals live in `report_quality_eval.toml` and cover the
reader-facing report-writing checklist, artifact separation, and reviewer
routing surfaces.
Codex subagent role evals are implemented by `evaluate_codex_agent_roles.py`
and cover each `.codex/agents/*.toml` role's expected behavior, forbidden
behavior, model / reasoning bucket, task-routing defaults, optional runtime
metrics, and whether output-use evidence is available.
Accumulated eval result families are declared in
`eval_result_families.toml`. Treat that registry as the abstract contract
between eval producers, archive paths, filename / run-id checks, and consumers
such as `eval_accumulation_check.py` and dashboards.
The checker must not need a new code branch for every future eval domain.
Add a registry family for structural analysis, writing-flow analysis, routing
analysis, role behavior, local-LLM responsibility, or other non-code evidence,
then have the producer emit reports that satisfy the declared filename and
run-id contract.

Use these evals when changing a skill, workflow, or routing prompt:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml
```

When a run uses skills, run the same prompt eval with accumulated evidence.
Detailed reports are stored in the mounted runtime log archive under
`.agent-canon/archive/<env-key>/eval-results/skill-workflow-prompt/` and are never
overwritten during normal agent work:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml \
  --accumulate \
  --run-id <run-id> \
  --skill-used agent-orchestration
```

The file name convention is:

```text
<eval_run_id>-<status>-<skill-slug>.md
```

`eval_run_id` is assigned by the tool as
`skill-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>`.
The machine-readable output includes `EVAL_RUN_ID=<eval_run_id>`,
`EVAL_USED_SKILLS=<comma-separated-skills>`, and
`EVAL_ACCUMULATED_REPORT=<path>` for accumulated runs.
Run-bundle behavior evals reject placeholder values; the accumulated report
path must exist and contain the matching eval run id.
If an explicitly requested `--report-out` path already exists, the tool writes a
sibling path with the same `eval_run_id` appended instead of overwriting it.

An eval passes only when every critical checklist item passes and the manifest audit passes.
The manifest audit fails closed on duplicate eval IDs, duplicate explicit targets, and duplicate
checklist IDs within an eval.
The growth-candidate buckets are duplicate eval IDs, duplicate explicit targets, and duplicate checklist IDs.
Keep `EVAL_AUDIT_STATUS=pass` and `EVAL_GROWTH_CANDIDATES=0` before closing skill or workflow prompt
improvement work.
When a prompt surface needs additional coverage, add checklist items to the existing eval entry for
that target instead of adding a second explicit-target eval.
If an eval reports drift, fix the target prompt and rerun the same manifest until the report passes.

Use behavior evals before closeout to check that skills and workflows changed actual agent
behavior, not only text:

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest agents/evals/agent_behavior_eval.toml \
  --write
```

Behavior evals inspect `workflow_monitoring.md`, `agent_evaluation.md`, review artifacts,
closeout evidence, and validation logs. They require observable events such as skill invocation,
subagent routing, tool gates, accumulated prompt eval runs, feedback resolution, subagent lifecycle closeout,
static-analysis feedback, code checker results, execution path comparison, token footprint comparison, and diff-check decisions.
Record code checkers as behavior events, for example
`tool_call=pyright code_checker=pass`, `tool_call=ruff code_checker=pass`,
`tool_call=oop-readability-check code_checker=pass`, or
`code_checker_not_required` for non-changing advisory runs.
Hook and tool outcomes must also close the protocol feedback loop. Record
`hook_tool_feedback=reviewed`, `parent_protocol_update=<applied|recorded|not_required>`,
`subagent_protocol_update=<applied|recorded|not_required>`, and
`protocol_feedback_reason=...` so the run shows whether parent workflow rules,
subagent handoff rules, role TOML, evals, or memory changed because of the
observed results.
Hook outcomes and accumulated eval reports use the external runtime log archive
documented in `documents/runtime-log-archive.md`. Hook entries carry unique
`hook_run_id` values. Normal hook writers shard JSONL files by source repo key
and runtime namespace under
`.agent-canon/archive/<env-key>/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl`
so multiple containers or template-derived repositories do not append to one
conflicting AgentCanon source-tree filename. AgentCanon source does not keep an
`agents/evals/results/` tree. Tools do not use that historical path as a normal
read or write location; old results must be imported into the archive and
deleted from source.
Run `python3 tools/agent_tools/eval_accumulation_check.py --root .` before
using accumulated evidence in a PR or guide. The gate validates directory
mounted JSONL readability when available, every family declared in
`eval_result_families.toml`, unique run ids, non-ignored tracked evidence
paths, and intentionally ignored archive paths, without compacting or deleting
archive results.
Local LLM responsibility prompt evals are configured separately:

```bash
agent-canon local-llm eval \
  --manifest agents/evals/local_llm_responsibility_eval.toml
```

Use `--accumulate` to write a uniquely named report under
`.agent-canon/archive/<env-key>/eval-results/local-llm-responsibility/`. Use
`--run-llm` only when the local llama.cpp runtime is intentionally available; CI
and static gates keep the model-backed step optional and evaluate prompt
boundaries only.
Workflow selection evals are configured separately:

```bash
python3 tools/agent_tools/evaluate_workflow_selection.py \
  --manifest agents/evals/workflow_selection_eval.toml
```

Use `--accumulate` when the workflow-routing measurement itself should become
durable AgentCanon evidence under
`.agent-canon/archive/<env-key>/eval-results/workflow-selection/`.
Reports list case IDs, expected workflow labels, and observed workflow labels;
they do not store the raw prompt text.
Report quality evals are configured separately:

```bash
python3 tools/agent_tools/evaluate_report_quality.py \
  --manifest agents/evals/report_quality_eval.toml
```

Use `--accumulate` when the report-writing checklist measurement itself should
become durable AgentCanon evidence under
`.agent-canon/archive/<env-key>/eval-results/report-quality/`.
Reports list checklist IDs and missing patterns; they do not store raw report
drafts or prompts.
Codex subagent role evals are configured separately:

```bash
python3 tools/agent_tools/evaluate_codex_agent_roles.py
```

The role eval fails when a role TOML is unregistered, over-costed for its bucket,
missing a read-only or findings-first prohibition, or routed before cheaper
language / diff-triage reviewers. Optional JSONL runtime metrics can be supplied
with `--runtime-log <path>` using fields such as `agent`, `tokens`,
`latency_ms`, `retry_count`, `parent_intervention`, `format_violation`, and
`output_used`. When no runtime metric log exists, the eval reports
`ROLE_RUNTIME_METRICS_STATUS=missing` without failing; this keeps old logs
append-only while making the measurement gap visible.
Use `--accumulate` when role routing or model policy changes should become
durable evidence under
`.agent-canon/archive/<env-key>/eval-results/codex-agent-role/`:

```bash
python3 tools/agent_tools/evaluate_codex_agent_roles.py --accumulate
```

The accumulated role report uses
`codex-agent-role-eval-<YYYYMMDDTHHMMSSffffffZ>-<10-char-sha256-prefix>-<status>.md`
and records `CODEX_AGENT_ROLE_EVAL_RUN_ID=<eval_run_id>`.
GitHub Actions reads these hook results recursively, memory notes,
skill eval reports, and `issues/open|closed/` to generate a read-only Agent Improvement Guide on PRs and branch pushes.
That guide must not stop at raw pass/fail counts: it summarizes skill usage,
candidate skill / workflow / tool routing inferred from prompts, human feedback
labels and targets, explicit human feedback labels, skill/event coverage, hook
source files, hook tool names, code-checker target paths, repeated failure
fingerprints, and hook-quality
counters such as unknown events, empty skill observations, fallback payloads, or
skill usage entries that did not update workflow monitoring.
Prompt-intake logs must not store unbounded raw prompt text. Store bounded,
redacted excerpts, fingerprints, and counts so routing evidence is useful
without turning the archive into a transcript store.
When two runs can choose different paths, compare them with
`tools/agent_tools/compare_agent_run_paths.py` and record its
`execution_path_comparison`, `route_efficiency`, `selected_inefficient_route`,
and `static_analysis_feedback` tokens in `workflow_monitoring.md`.
When token reduction is part of the objective, activate the token-efficiency protocol,
compare Codex session footprints with `tools/agent_tools/compare_codex_token_footprints.py`,
and record the resulting token ratio in `workflow_monitoring.md`. For runs that do not
target token reduction, record the explicit `token_efficiency_not_required` opt-out instead
of omitting the behavior family entirely.
Record these events during the run with
`tools/agent_tools/workflow_monitor.py --behavior-event "..."` instead of reconstructing them only
at closeout.
