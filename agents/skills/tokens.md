# tokens
<!--
@dependency-start
contract skill
responsibility Owns token budget, equivalent baseline, role footprint, and efficiency decisions for Codex repository work.
upstream design ../canonical/CODEX_WORKFLOW.md task execution and closeout contract
upstream design ../canonical/CODEX_SUBAGENTS.md subagent routing and role contract
upstream design ../COMMUNICATION_PROTOCOL.md bounded context and handoff contract
upstream implementation ../../.codex/config.toml shared runtime limits and defaults
upstream implementation ../../eval/checkers/compare_codex_token_footprints.py equivalent session comparison
upstream implementation ../../eval/producers/evaluate_codex_agent_roles.py observed role evidence
downstream design ./agent-log-analysis.md structured token evidence routing
downstream design ./agent-eval-accumulation.md accumulated eval evidence route
@dependency-end
-->

## Reader Map

- Purpose: make token use an evidence-based execution decision without
  weakening the task contract or required validation.
- Use When: an observed role footprint, context reuse, tool output limit,
  model effort, or token-efficiency claim is being measured or reviewed.
- Boundary: this skill does not classify tasks, define role defaults, own
  context construction, produce metrics, store eval artifacts, or publish
  runtime logs.

## Purpose

Token efficiency is a measured runtime property. This skill establishes an
equivalent baseline, records the measured role footprint, and decides whether
an efficiency change is supported by observed evidence. A shorter prompt,
smaller role list, or successful task is not by itself a token reduction.

## Activation

Activate this skill only when observed token-efficiency evidence exists or the
user explicitly requests a token-efficiency measurement or decision. A normal
task budget, role footprint, or adaptive execution decision does not activate
this skill by itself. Duplicate reads, repeated role decisions, unused review
output, oversized tool output, malformed handoffs, and retries are evidence
for activation when they are observed; the skill does not infer them from task
size.

## Budget and Measured Footprint

1. Read `.codex/config.toml` and the selected `agents/task_catalog.yaml` family
   for its existing token budget. Record the actual role footprint, packet
   reuse, and output envelope from the execution evidence; do not choose a
   profile or team shape from a task-size estimate.
2. Record which producer, reviewer, and implementation roles actually ran,
   their distinct decision IDs, and whether their outputs were used. Do not
   materialize roles, assign reviewers, or change the team topology here.
3. Keep the observed footprint tied to the task's distinct decisions and
   equivalent validation obligations. Duplicate reads or perspectives are
   evidence for an efficiency decision, not a reason for this skill to launch
   another role.
4. `worker` / `spark_worker` selection, role activation, team construction, and
   context packets belong to `$agent-orchestration` and `$subagent-bootstrap`.
   This skill consumes their route evidence and measures its token footprint.

## Baseline and Efficiency Decision

Compare equivalent behavior envelopes: the same task intent, validation
obligations, role responsibilities, and usable output. An equivalent envelope
and both source sessions are required before a reduction claim can be made.
Call the existing token-footprint checker and role evaluator, preserve their
structured artifacts through the normal result-artifact route, and do not
introduce another metric or acceptance threshold. Record the source sessions,
envelope, totals, ratio, and behavior-evaluation result. Without a post-change
candidate session or another required measurement, report the effect as
`unmeasured` and make no reduction claim.

Decide whether a model-effort, profile, team, or output-limit change is
supported only after observed runtime evidence identifies that surface as the
cause. Hand the selected change to `$agent-orchestration` or
`$subagent-bootstrap`; apply profile changes in a fresh session and do not
encode machine-local values in repository docs. Required validation, review,
and closeout evidence remain required even when an efficiency change is
accepted.

## Evidence Owners

- `eval/checkers/compare_codex_token_footprints.py` owns equivalent baseline
  and candidate session comparison.
- `eval/producers/evaluate_codex_agent_roles.py` owns observed per-role calls,
  tokens, latency, retries, parent interventions, format compliance, and output use.
- `eval/producers/generate_agent_runtime_dashboard.py` owns accumulated trends.
- `$agent-log-analysis` owns structured dashboard interpretation and routes a
  `token_coverage` finding here.
- `$agent-eval-accumulation` owns registered producer execution and archive
  accumulation; `$result-artifact-writeout` owns durable artifact placement.

Do not hand-write a token report, create a per-wave token schema, or claim a
reduction from missing evidence.

## Adaptive Triggers and Route

Record an efficiency decision when evidence shows duplicate role decisions,
repeated reads of one source, unused reviewer output, oversized raw tool output,
malformed-handoff retries, or model/effort mismatch. Classify the cause first;
a review rejection or validation failure does not automatically expand the team
or change the profile. Route any resulting role, team, or context change to
`$agent-orchestration` or `$subagent-bootstrap`.

For a token finding, carry the evidence cell, equivalent envelope, source
sessions, owner decision, and selected validation to the next packet. Route
missing metrics to the existing producer/eval owners. Route recurrence feedback
to `$agent-learning` and structured log interpretation to
`$agent-log-analysis`; do not absorb either responsibility here.

## Closeout

Report the selected budget and role footprint, baseline/candidate identity,
equivalence envelope, totals and ratio when measured, behavior-eval result, and
any unmeasured field. Use the normal owner-selected validation for every
changed responsibility and its normal closeout route. Token evidence cannot
replace dependency review, static analysis, diff review, required checks, or
pushed commits for a repository change.

## Runtime Contract Clauses

1. Read the selected configuration and task-family budget before measuring the
   role footprint or deciding on efficiency; do not infer either from task-size
   estimates.
2. Record the roles, distinct decisions, packet reuse, and output use selected
   by the orchestration owners; do not activate roles or construct packets here.
3. Compare equivalent behavior envelopes with the existing checker and role
   evaluator. Record missing post-change candidate evidence as `unmeasured`.
4. Delegate worker/team/context selection to `$agent-orchestration` and
   `$subagent-bootstrap`; delegate metric production, eval execution, artifact
   storage, and dashboard accumulation to their existing owners.
5. Treat token efficiency as supporting evidence. Preserve required behavior,
   validation, review, cleanup, and publication obligations.
