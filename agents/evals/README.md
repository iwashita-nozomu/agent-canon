<!--
@dependency-start
responsibility Documents skill and workflow prompt eval definitions.
upstream design ../canonical/skills.md skill canon registry
downstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py runs these evals
downstream implementation ../../tools/agent_tools/evaluate_agent_run.py runs behavior evals
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

Use these evals when changing a skill, workflow, or routing prompt:

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest agents/evals/skill_workflow_prompt_eval.toml
```

When a run uses skills, run the same prompt eval with accumulated evidence.
Detailed reports are stored in
`agents/evals/results/skill-workflow-prompt/` and are never overwritten during
normal agent work:

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
Hook outcomes accumulate under `agents/evals/results/hook-runs/` with unique
`hook_run_id` values. Normal hook writers shard JSONL files by runtime namespace
under `hook-runs/<runtime-namespace>/<hook-name>.jsonl` so multiple containers
or template-derived repositories do not append to one conflicting filename.
GitHub Actions reads these hook results recursively, memory notes,
skill eval reports, and `issues/open|closed/` to generate a read-only Agent Improvement Guide on PRs and branch pushes.
That guide must not stop at raw pass/fail counts: it summarizes skill usage,
skill/event coverage, hook source files, hook tool names, code-checker target
paths, repeated failure fingerprints, and hook-quality counters such as
unknown events, empty skill observations, fallback payloads, or skill usage
entries that did not update workflow monitoring.
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
