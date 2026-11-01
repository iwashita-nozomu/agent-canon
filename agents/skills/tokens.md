# tokens
<!--
@dependency-start
contract skill
responsibility Owns token budget, equivalent baseline, role footprint, and efficiency decisions for Codex repository work.
upstream design ../canonical/CODEX_WORKFLOW.md task execution and closeout contract
upstream design ../canonical/CODEX_SUBAGENTS.md subagent routing and role contract
upstream design ../COMMUNICATION_PROTOCOL.md bounded context and handoff contract
upstream implementation ../../.codex/config.toml shared runtime limits and defaults
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/token_footprints.rs equivalent session comparison
upstream implementation ../../eval/producers/evaluate_codex_agent_roles.py observed role evidence
downstream design ./structure-refactor.md repairs independently activated responsibilities coupled into one read
downstream design ./agent-log-analysis.md structured token evidence routing
downstream design ./agent-eval-accumulation.md accumulated eval evidence route
@dependency-end
-->

## Reader Map

- Purpose: locate avoidable context or token work without changing the task
  contract.
- Use When: token/context diagnosis is requested or repeated inefficiency is
  observed; task size alone is not a trigger.
- Boundary: the caller supplies the task context; existing owners define metric,
  collection, and runtime routes.

## Method

Start from the caller's goal and the context already available. Use known facts,
the current revision, metrics, or target role only as relevant. On a resumed or
compressed context, retain why completed fixes were accepted and what unit
remains. Continue that unit without reopening finished work or restoring a
rejected approach. Re-read only a truncated relevant part or check a specific
missing fact when it could change the action; do not reopen the full history.
Do not re-compress context just to make it shorter when no task-relevant
information or handoff needs it.

Identify a concrete repeated read, decision, unused output, retry, or other
source-supported waste; follow it to its owner and repair it with the owner's
normal validation. A supported waste repair does not need comparison sessions.
Shorter text, fewer roles, or a successful task alone does not prove token
savings. Keep the task's required behavior and checks intact.

Missing counters or incomplete coverage remain unknown or `unmeasured`, not
zero. Do not automatically collect logs, sync archives, repair dashboards,
rerun producers, or launch comparison sessions. Change a model, window, runtime,
or profile only when observed evidence identifies that setting as the cause.

## Quantitative claims

A reduction claim needs actual before-and-after sessions with equivalent task
intent, validation obligations, role responsibilities, and usable output. Use
actual counters from the existing footprint route; do not estimate savings from
shorter instructions or task success. If sessions or required measurements are
missing, report `unmeasured`, not zero or a reduction. Reuse existing results;
do not create an unrelated baseline or a new metric/threshold.

## Conditional owner routes

- For a budget or runtime-limit question, consult `.codex/config.toml` and the
  relevant task family only as needed. Team, role, and context choices belong to
  `$agent-orchestration` and `$subagent-bootstrap`.
- For an actual session comparison, reuse or select
  `tools/bin/agent-canon compare-codex-token-footprints`. Use
  `eval/producers/evaluate_codex_agent_roles.py` only when role attribution is
  unresolved. For an accumulated trend question, use existing dashboard
  summaries and `eval/producers/generate_agent_runtime_dashboard.py` as its
  owner; run collection or repair through `$agent-eval-accumulation` only when
  selected.
- For unresolved log interpretation, use `$agent-log-analysis` with bounded
  evidence. Durable output uses `$result-artifact-writeout` when requested.
- If mixed file responsibilities force unrelated reading, use
  [structure-refactor](structure-refactor.md#overloaded-documents) when a
  responsibility change is warranted. Use the existing
  [communication protocol](../COMMUNICATION_PROTOCOL.md) for a selected handoff;
  do not introduce a context capsule, manifest, schema, or new gate.

## Closeout

Answer in the caller's requested form, separating observation from inference
and stating limits that affect the conclusion. For measured savings, identify
the actual sessions and equivalence basis. Token evidence does not replace
required task validation or authorized delivery.
