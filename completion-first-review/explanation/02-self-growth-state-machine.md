# Self-Growth State Machine
<!--
@dependency-start
contract reference
responsibility Defines the self-growth state machine for completion-first AgentCanon improvements.
upstream design ../README.md completion-first review index
upstream design 00-completion-first-principle.md completion-first rationale
upstream design ../../agents/workflows/agent-learning-workflow.md agent learning workflow
upstream design ../../agents/workflows/adaptive-improvement-workflow.md adaptive improvement workflow
upstream implementation ../../tools/agent_tools/evaluate_agent_run.py current agent run evaluator
upstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py current prompt evaluator
@dependency-end
-->

## Purpose

Self-growth is the most important long-term capability for AgentCanon, but self-growth must not mean unlimited memory growth or vague prompt additions. It must mean that observed failures are turned into verified repairs.

The required state machine is:

```text
Observe -> Diagnose -> Repair -> Evaluate -> Replay -> Promote -> Retire
```

Each step must have an artifact. If a step is skipped, the task is not complete under the `self_growth` closeout profile.

## Reader Map

Use this document to answer how observed agent failures become verified
self-growth repairs. Read Purpose first for the state sequence, then S1 through
S7 in order: Observe, Diagnose, Repair, Evaluate, Replay, Promote, Retire. The
last sections define the repair manifest, completion gate, and invariant that
prevents vague prompt additions from counting as complete repair.

## S1: Observe

Observation records what happened.

Sources:

- user feedback,
- reviewer feedback,
- tool failure,
- eval failure,
- MCP failure,
- runtime limitation,
- recurring review finding,
- discovered false negative.

Required event fields:

```yaml
source: user | reviewer | tool | eval | runtime
feedback_type: preference | quality_failure | process_failure | tool_gap | prompt_gap | false_positive_gate | false_negative_gate | style_request | domain_rule
severity: low | medium | high | critical
evidence: short pointer to the observed issue
target_hint: skill | workflow | tool | schema | memory | unknown
```

Bad observation:

```text
The user wanted this to be better.
```

Good observation:

```yaml
source: user
feedback_type: quality_failure
severity: high
evidence: user requested deeper root-cause review and violation cases
target_hint: completion profile / self-growth workflow
```

## S2: Diagnose

Diagnosis explains why the failure happened.

Root-cause categories:

- `routing_gap`: wrong workflow or skill selected,
- `skill_prompt_gap`: selected skill lacks required instruction,
- `workflow_prompt_gap`: workflow does not require the right artifact,
- `tool_gate_gap`: verifier cannot detect the failure,
- `artifact_schema_gap`: file can exist while content is empty or meaningless,
- `closeout_profile_gap`: wrong profile or missing required gate,
- `eval_gap`: eval does not cover the failure,
- `memory_gap`: learning is not durable or not propagated,
- `runtime_limitation`: current runtime cannot enforce desired behavior.

Diagnosis must include why the selected cause is more plausible than alternatives.

Bad diagnosis:

```text
Need to be stricter.
```

Good diagnosis:

```yaml
failed_invariant: completion cannot be self-attested
root_cause_category: closeout_profile_gap
why_this_cause:
  - current closeout uses status tokens that can be hand-written
  - no profile distinguishes self-growth from standard work
why_not_other_causes:
  - not only a prompt gap because the verifier must reject token-only completion
```

## S3: Repair

Repair chooses the surface to change.

Allowed repair types:

- `prompt_repair`,
- `workflow_repair`,
- `tool_repair`,
- `schema_repair`,
- `eval_update`,
- `memory_record`,
- `no_op` with explicit reason.

Important rule:

A `tool_gap` or `false_negative_gate` must not be closed by prompt repair alone. It requires tool, schema, or eval repair.

Examples:

| Feedback type | Minimum repair surface |
| --- | --- |
| style_request | memory or prompt |
| prompt_gap | prompt and eval |
| workflow_prompt_gap | workflow contract and eval |
| artifact_schema_gap | schema and verifier |
| tool_gate_gap | tool and negative fixture |
| false_negative_gate | tool/schema/eval and replay |
| memory_gap | memory propagation and submodule evidence |

## S4: Evaluate

Evaluation checks the changed surface.

Examples:

- skill or workflow prompt changed -> run prompt eval,
- behavior rule changed -> run behavior eval,
- tool changed -> run unit test and tool catalog check,
- schema changed -> run schema validator,
- memory changed -> run memory persistence checks,
- completion rule changed -> run completion verifier fixture tests.

The same eval that failed or should have failed must be rerun. Passing a different eval is not enough.

Required fields:

```yaml
baseline_eval_ids: []
rerun_eval_ids: []
expected_fail_before: []
expected_pass_after: []
```

## S5: Replay

Replay proves the repair changes behavior.

Every self-growth repair should add at least one negative case and one positive case unless a written exception is accepted.

Negative replay case:

- represents the old false negative,
- should fail after the repair,
- documents why it used to pass or be ambiguous.

Positive replay case:

- represents the correct new path,
- should pass after the repair,
- prevents overcorrection.

Example:

```yaml
negative_case:
  id: token-only-ci-pass
  fixture_type: run_bundle
  expected_new_status: fail
  reason: tool_call event has no evidence_path or exit_code

positive_case:
  id: command-backed-ci-pass
  fixture_type: run_bundle
  expected_new_status: pass
  reason: tool_call event includes command, exit_code, hashes, and evidence_path
```

## S6: Promote

Promotion decides whether the learning becomes durable canon.

Promotion targets:

- memory,
- skill,
- workflow,
- AGENTS or ROOT_AGENTS,
- tool gate,
- schema,
- no promotion.

Promotion requires scope. Not all learning is repo-wide.

Required fields:

```yaml
promotion_candidate: true | false
target: memory | skill | workflow | AGENTS | tool | schema | none
scope_limit: repo-wide | task-family | local
support_count: integer
counterexample_review: pass | fail | not_applicable
```

A single user preference should not become a repo-wide invariant unless the user explicitly marks it durable or it is supported by repeated evidence.

## S7: Retire

Self-growth must include removal. Otherwise the canon only grows.

Every durable learning item should eventually have one of:

- `review_after`,
- `expiry`,
- `superseded_by`,
- explicit reason that no retirement is appropriate.

Retirement examples:

- old runtime workaround,
- duplicate rule,
- prompt guidance replaced by tool gate,
- model-specific workaround,
- temporary MCP limitation,
- obsolete Template migration rule.

## Self-growth repair manifest

The central artifact should be:

```yaml
version: 1
kind: self_growth_repair_manifest
trigger:
  source: user
  feedback_type: quality_failure
  severity: high
  evidence: "..."
diagnosis:
  failed_invariant: "..."
  root_cause_category: closeout_profile_gap
  why_this_cause: []
  why_not_other_causes: []
repair:
  repair_type: schema_repair
  touched_files: []
eval:
  baseline_eval_ids: []
  rerun_eval_ids: []
  expected_fail_before: []
  expected_pass_after: []
replay:
  negative_cases_added: []
  positive_cases_added: []
  replay_status: pass
promotion:
  promotion_candidate: true
  target: workflow
  scope_limit: repo-wide
  counterexample_review: pass
retirement:
  review_after: ""
  supersedes: []
closeout:
  self_growth_status: pass
```

## Completion gate

The `self_growth` closeout profile should fail if any of these are missing:

- structured runtime feedback when feedback exists,
- learning diagnosis,
- repair manifest,
- negative case or explicit exception,
- positive replay or explicit exception,
- prompt/workflow/tool/schema eval evidence,
- promotion or no-promotion decision,
- retirement or review-after decision,
- memory propagation evidence when memory changed.

## Key invariant

```text
A self-growth task is not complete when it writes a lesson. It is complete when it prevents a known failure from passing again.
```
