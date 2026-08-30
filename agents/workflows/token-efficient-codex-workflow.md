<!--
@dependency-start
contract workflow
responsibility Documents evidence-driven token reduction for Codex repo work.
upstream design ../canonical/CODEX_WORKFLOW.md Codex runtime workflow contract
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent routing contract
upstream implementation ../../.codex/config.toml defines shared runtime limits
downstream design README.md workflow catalog references this overlay
@dependency-end
-->

# Token-Efficient Codex Workflow

This overlay reduces repeated agent decisions, duplicated context copies, and
oversized tool output while preserving every request clause and owner-required
artifact. Context construction remains owned by
`agents/COMMUNICATION_PROTOCOL.md`; the context needed for the next decision may
be large.

Token reduction is a measured runtime claim. Compare equivalent session or
role evidence, preserve behavior and skill accuracy, and report missing
candidate evidence as missing. A smaller configured role list or shorter prompt
does not prove a token reduction.

## Reader Map

- This overlay owns token observation, adaptive role materialization, reduction
  evidence, and closeout claims.
- Read `## Adaptive Execution` before changing fan-out, model effort, or tool
  output limits. Use `## Context Protocol Use` for handoff construction and
  `## Existing Metric Owners` for attribution.
- It does not own task classification, context-size caps, role model defaults,
  or new token schemas.

## Adaptive Execution

- Start from `.codex/config.toml`, `.codex/agents/*.toml`, and the selected
  workflow family's `4/2` budget. Do not choose a profile or team shape from a
  task-size estimate.
- Materialize the producer for the active decision, then the reviewer selected
  by that decision's artifact. A specialist without a distinct decision,
  `review_focus`, input packet, and expected output stays inactive.
- Keep one physical agent accountable for one decision. Multiple perspectives
  require distinct decision IDs and non-duplicated packets.
- Use `worker` for implementation. Use `spark_worker` only when the typed parent
  packet records the approved mechanical responsibility unit and selection
  evidence.
- The `.codex/config.toml` `gpt-5.6-sol/high` parent is the orchestrator only.
  Every repository-changing task uses a write-capable child; launch blockers
  produce typed blocked/retry/user-report evidence and never a parent write.
- Change model effort, user-level profile, or output limit only after observed
  runtime evidence identifies that surface as the cause. Apply profile changes
  in a fresh session; do not encode machine-local values in repository docs.

## Context Protocol Use

- Follow `agents/COMMUNICATION_PROTOCOL.md` for context visibility, repository
  investigation packets, parent orchestration, and fresh subagent capsules.
- For tool-covered questions, call the canonical checker, router, semantic
  index, dashboard, or structured report before prose review or subagent
  handoff. Treat pass/finding output as the authority for that covered property.
- Read exact owner paths, dependency headers, and named upstream files after a
  tool artifact or protocol packet identifies the needed context.
- Hand structured tool artifacts to subagents through path references in the
  protocol-owned capsule; do not ask them to re-run deterministic checks by
  reading the same documents.
- Store long raw outputs in the run bundle and pass their artifact paths,
  clause IDs, and section names instead of chat summaries.
- Keep tool output structured and targeted. The project-level
  `tool_output_token_limit` bounds one output, but does not authorize omitted
  evidence or fragmented semantic units.
- If a canonical tool lacks the abstraction needed for routing, extend the tool
  or record the tool-contract gap instead of compensating with broad manual
  reading.

## Existing Metric Owners

- `eval/checkers/compare_codex_token_footprints.py` owns equivalent baseline
  and candidate session comparison.
- `eval/producers/evaluate_codex_agent_roles.py` owns observed per-role calls,
  tokens, latency, retries, parent interventions, format compliance, and output
  use.
- `eval/producers/generate_agent_runtime_dashboard.py` owns accumulated
  trends.
- Record the compared envelope, source sessions, totals, ratio, and behavior
  eval result. Do not introduce another per-wave token schema or hard acceptance
  threshold.
- Accept a claimed improvement only when equivalent behavior evidence does not
  regress. Without a post-change candidate session, report the effect as
  unmeasured.

## Adjustment Triggers

Adjust the next decision packet when evidence shows duplicate role decisions,
repeated reads of the same source, unused reviewer output, oversized raw tool
output, retries caused by malformed handoffs, or a model/effort mismatch. A
review rejection or validation failure changes the next packet only after its
cause is classified; it does not automatically expand the team or profile.

## Closeout

Token-efficient mode still requires the normal closeout evidence:

- dependency review for the full repo when required by `AGENTS.md`
- static analysis / CI appropriate to the task
- diff-check review when the task is repo-changing
- no unfinished planned work
- pushed commits when the task changes shared canon or template state

Do not trade required validation for a token claim. Run the validation selected
by the changed responsibility unit and active runtime profile, and keep missing
candidate token evidence explicit.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/validation/semantic/convention/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
