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

- Purpose: diagnose overhead and measure token efficiency without weakening
  the task contract or required validation.
- Use When: requested token diagnosis/measurement or observed efficiency problems.
- Boundary: task classification, role defaults, context construction, metrics,
  artifact storage, and runtime publication remain with their existing owners.

## Purpose

An unnecessary operation and a measured token reduction are different claims.
Logs and source can establish the former without a post-change session. A
shorter prompt, smaller role list, or successful task alone proves no reduction.

## Activation

Activate for explicit token diagnosis/measurement or observed duplicate reads,
repeated decisions, unused output, oversized tool output, or retries; not for a
normal task budget, task size, or adaptive execution decision alone.

Start with existing summaries/API and a named snapshot. Reuse applicable results
and use bounded drilldown through `$agent-log-analysis` for unresolved questions.
Missing counters limit quantitative claims, not other supported observations.
Do not automatically collect logs, sync archives, repair dashboards, rerun evals,
or launch comparison sessions to fill gaps. Select further collection only when
the requested decision needs it and it is authorized. Unknown is not zero use.

## Budget and Measured Footprint

Read `.codex/config.toml` and the selected `agents/task_catalog.yaml` family only
for budget/runtime decisions, not as a prerequisite for describing existing logs.
For relevant role attribution, record roles that actually ran, distinct decisions,
packet reuse, and output use; registration or task size is not execution evidence.
`worker` / `spark_worker` selection, roles, teams, and context packets remain with
`$agent-orchestration` and `$subagent-bootstrap`; reuse their evidence instead of
launching a role merely for this report.

## Baseline and Efficiency Decision

A quantitative reduction claim requires both source sessions and equivalent
behavior envelopes: the same task intent, validation obligations, role
responsibilities, and usable output. Reuse applicable token-footprint checker
results, or call the checker when that comparison is selected. Use the role
evaluator only for unresolved role attribution, not for every diagnosis. Preserve
selected artifacts through the normal result-artifact route; add no metric or
acceptance threshold. Missing sessions or required measurements mean `unmeasured`,
not a reduction claim. Do not manufacture baselines by running unrelated tasks.

A source-supported unnecessary operation may be repaired by its existing owner
with normal validation while its token effect remains `unmeasured`. Change model
effort, profile, team, or output limits only when observed runtime evidence
identifies that surface as the cause. Delegate to `$agent-orchestration` or
`$subagent-bootstrap`; apply profile changes in a fresh session and do not encode
machine-local values in repository docs.

## Evidence Owners

- `eval/checkers/compare_codex_token_footprints.py`: equivalent session comparison.
- `eval/producers/evaluate_codex_agent_roles.py`: per-role calls, tokens, latency,
  retries, parent interventions, format compliance, and output use.
- `eval/producers/generate_agent_runtime_dashboard.py`: accumulated trends.
- `$agent-log-analysis`: structured interpretation and `token_coverage` findings.
- `$agent-eval-accumulation`: selected producer execution and accumulation;
  `$result-artifact-writeout`: durable artifact placement.

These references are not a mandatory execution sequence. Do not hand-write
numeric token reports or per-wave schemas. Diagnostic observations are not metrics.

## Adaptive Triggers and Route

Classify duplicate decisions/reads, unused reviews, oversized output,
malformed-handoff retries, or model/effort mismatch before choosing a repair.
Rejection or validation failure does not automatically expand the team or change
the profile. Carry the snapshot, observation, cause hypothesis, owner, and
selected validation to the owning route; add comparison evidence when measured.
Missing metrics identify an owner, not an instruction to run a producer.
Recurrence feedback belongs to `$agent-learning`.

## Closeout

For diagnosis, report observations separately from hypotheses, evidence scope,
selected repair, validation, and limits on the requested claim. Do not fill an
unused comparison-only ledger. For measured comparisons, report both sessions,
equivalent envelope, applicable budget/role footprint, totals, ratio, and
behavior-evaluation result; mark missing required measurements `unmeasured`.
Token evidence does not replace owner-selected dependency review, static analysis,
diff review, required checks, cleanup, pushed commits, or Issue/PR readback.

## Runtime Contract Clauses

1. Diagnose from existing summaries and a named snapshot with bounded drilldown.
   Missing metrics limit claims; collection, sync, repairs, eval reruns, and
   comparison sessions are not automatic prerequisites.
2. Read configuration/task-family budget only for budget/runtime decisions;
   inspect roles only when relevant. Task size is not evidence, and runtime
   changes require observed cause evidence.
3. Selected comparisons require equivalent envelopes and both sessions; reuse
   or run the existing checker. Use the role evaluator only for unresolved
   attribution. Missing measurements mean `unmeasured`, not a reduction claim
   or a blocker to a source-supported repair with normal validation.
4. Delegate team/context and selected metric/eval/artifact/archive work to
   existing owners. Do not launch roles or traverse all owners merely to fill
   a report; diagnosis requires no unused comparison ledger.
5. Preserve required behavior, validation, review, cleanup, and publication;
   token efficiency is supporting evidence, not a replacement.
