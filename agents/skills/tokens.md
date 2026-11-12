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

## Task workflow

1. Reuse the goal, source and accepted decisions. Fix the requested token metric
   and required task outcomes before a comparison. Carry already located target,
   consumer/test references and completed lookup results, with source revision and
   scope, in the existing handoff. Supply the raw source slices needed for the next
   decision, including affected fields' definitions and consumers; avoid a reading
   list of whole files or completed history. Additional
   reads remain available for a missing decision. Preserve these facts on resumption.
2. Inspect the selected sessions' actual counters and calls. Separate document
   reads, cached/fresh input, output, retries and tool calls; identify a concrete
   redundant read, oversized result or failed call. Obtain counters from existing
   runtime logs outside the task agent's work; do not add manual measurement to
   its deliverable. Keep missing data unmeasured and include new preparation work
   when claiming savings for an entire delegated workflow.
3. Repair that cause at its existing owner. Use
   [bounded reads](agent-orchestration.md#owner-first-read-trace) and
   [tool cooperation](agent-orchestration.md#skill-and-tool-cooperation) for
   search scope and batching. Keep required code, consumer and validation coverage.
   Do not change a model/window merely to compensate for unnecessary calls.
4. When empirical comparison is selected, freeze the same task, source, authority,
   model/effort and required outcomes under
   [empirical-prompt-tuning](empirical-prompt-tuning.md#workflow). Compare actual
   session counters and completed outputs, including nearby regression cases.
   Smaller documents alone do not establish lower total tokens. An unrelated
   built-in comparison threshold does not replace the agreed success criterion.
5. Adopt only a candidate meeting the requested metric and required outcomes;
   otherwise retain the supported result and fix the next observed cause. Record
   accepted/rejected revisions, sessions and limits in the existing Issue/result,
   then complete the selected formatting, delivery and application route.

A supported local waste repair needs no new comparison sessions unless the
requested claim depends on them. Log collection, archive repair and profile
changes remain separate selected operations; this workflow creates no ledger.

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
  `tools/bin/agent-canon evaluate-codex-agent-roles` only when role attribution is
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
