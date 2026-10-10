# Codex Completion

<!--
@dependency-start
contract agent-runtime
responsibility Owns completion evidence, validation, and delegation to the selected closeout owner.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
upstream design ../task_catalog.yaml bounded and coordination execution routes
@dependency-end
-->

## Reader Map

Reuse the execution route already selected from the task catalog. Read the common
completion requirement and the sections whose operation is active. Coordination
artifacts and state below apply only to `coordination`, not `bounded_fast_path`.

| When | Read |
| --- | --- |
| Assessing required outcome/evidence coverage | [Completion Bar](#completion-bar) |
| Performing selected validation | [6. Validation](#6-validation) |
| Closing a bounded route | [Bounded delivery](#bounded-delivery) |
| Closing a coordination run | [Mechanical Completion Loop](#mechanical-completion-loop) and [Coordination closeout](#coordination-closeout) |
| Consuming a coordination CompletionCoverage projection | [CompletionCoverage applicability](#completioncoverage-applicability-and-state-contract) |
| Reporting or handing off the result | [Completion Readiness](#completion-readiness) |

## Completion Bar

Account for all active request clauses, the complete affected responsibility unit,
selected validation, activated review, and authorized publication/cleanup. Preserve
the agreed target and required input domain rather than calling an incomplete
slice complete. Each material result has its actual operation and evidence.
Necessary path/link presence, forbidden legacy-path absence, and sufficient
behavior are different claims; select the evidence the changed contract requires.

Review source against equations, specifications, invariants, and assumptions when
present. Treat review suggestions as hypotheses: settle them against current
source, reachable behavior, and a witness or sound analysis. Repair accepted
in-scope findings while preserving intent; record verified rejection, escalation,
and unresolved claims with their effects on completion. Recheck only changed or
invalidated evidence. When Local Capability Priority was selected, retain its
[existing record](../skills/agent-orchestration.md#local-capability-priority).

An implemented, published, or handed-off result is not automatically verified or
applied. An unmet requirement returns to its next owning action through
[Completion Readiness](#completion-readiness), rather than becoming a terminal
response with a remaining-work list. Unrelated checks and other Issues do not
become completion prerequisites.

## Bounded delivery

For `bounded_fast_path`, use the existing task/Issue or structured handoff to
carry the requested work and applicable completion evidence. Record the exact
diff and selected checks; include an activated review only when one was selected.
If the request includes base integration or publication, carry its current-base
and authorized remote readback. Clean up only task-owned resources created by
the selected operations. Decide commit and push under
[delivery ownership](ROOT_DELIVERY.md#commit-and-push-decisions).

The selected results are the evidence. This route creates no coordination run
bundle, `user_request_contract.md`, `schedule.md`, `closeout_gate.md`, or
CompletionCoverage ledger, and does not call `task_close.py`. A concrete new
coordination need returns only that changed decision to the route owner; labels,
links, and report length do not initiate a route change.

## Mechanical Completion Loop

For a selected coordination run, use the existing run bundle and `closeout_gate.md`.
Read current active clauses, planned units, accepted findings, validation gaps, and
selected commit/push, synchronization, and follow-up outcomes. Inspect the final
tracked/untracked diff and directly affected dependencies/consumers. Run selected
static and targeted checks; select broad execution only when the affected contract
requires it and it can resolve a remaining decision.

An activated owning review gate may request a read-only diff-check. Give it the
current source, selected handoff, validation, and dependency evidence. The owning
reviewer adjudicates hypotheses and reopens only an accepted, source-backed
in-scope repair. Preserve the intent through repair, redesign, or authorized
escalation. Use [review activation and adjudication](../skills/agent-orchestration.md#review-activation-and-adjudication)
for those decisions.

`task_close.py` consumes the selected stage evidence and closeout inputs as the
coordination run's sole terminal readiness predicate. Record `not_applicable`
only where the selected run schema requires an inactive gate's disposition;
this does not activate the gate or a second evidence ledger.

## CompletionCoverage Applicability And State Contract

This section applies to coordination runs using CompletionCoverage. Existing
ledger owners append facts; the W2 projection/check boundary derives the read
model; `task_close` and `report_artifact_checks` consume it. Readers do not write
back to the schema owner or define a second state machine.

The state comprises `context_binding`, `coverage_map`, `gate_evidence`,
`failure_response`, `completion_boundary`, and `projection_metadata`. Preserve
transitions `context_bound` → `design_pending` → `design_approved` →
`writer_release_pending` → `writer_released` → `source_freeze_pending` →
`source_frozen` → `change_review_pending` → `change_review_approved` →
`integration_pending` → `publication_ready` → `delivered`. Validation failure
enters `repair_pending`; same-intent repair returns to its owner and unresolved
or intent-changing work enters `escalation_pending`.

`evaluate_completion_boundary` consumes one `control_topology_ledger.json`
snapshot for routing/publication, with schedule, open-work, repair, and crossing-edge
inputs. Parent-route and global-publication facts are not separate duplicate
inputs. Keep `all_planned_chunks_complete` and `overall_delivery_complete`
independent; a chunk or checkpoint is an internal progress observation.

W2-20 orders W2 design `APPROVE`, one isolated-branch writer release with collision
preservation and `branch_creation_reason=convergence_w2_gate_completion_authority`,
source freeze/review, then W3/integration-executor integration. Later
`routing_gate=verified` evidence is not a prerequisite for the writer action
that produces integration evidence.

W1 produces `ExecutionResourcePlan`. W2 consumes its W2-12 plan/actual/readback/
failure certificate mapping and W2-19 ordered GPU consumer mapping: candidate UUIDs,
process-held PID/start identities, active reservations, selected UUIDs, atomic
lock/lease and post-lock readback, effective environment, terminal GPU identities,
release/descendant retention, and typed insufficient-eligible or mismatch failure.
W2 does not select/reserve resources, parse NVML, construct environments, or
reimplement their tests and gates.

## 6. Validation

Use the changed contract's selected profile/check matrix and the common
[formatting and verification boundary](../../ROOT_AGENTS.md#validation-routing).
静的解析、読み取り確認、docs / targeted tests / agent checks を、変更契約と残るリスクから選びます。
Record final-source formatter/check and selected static/targeted evidence once;
later edits or integration invalidate only the affected evidence. Separate CI,
format, and synthetic checker-retest paths are not extra completion predicates.

For dependency/header changes, use the existing source-derived checks and relevant
downstream review. Select a whole-repository dependency review only when the
changed contract or explicit request requires it. Shared canon, Large Delivery,
and high-risk labels alone do not request every repository check.

Immediately after failed verification, update the
[failed verification topic](../../documents/operations/notes-lifecycle.md#failed-verification-record)
and read back that saved record. Keep observation and established cause distinct.
Preserve the selected profile's `failing_contract`, `observation_level`,
`cause_classification`, `intent_preservation`, and evidence in its existing record;
the taxonomy belongs to the
[profile/check matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md).
Repair a demonstrated in-scope cause or record the exact unavailable operation
and next owner/action. Continue independent authorized work without upgrading
unrun checks to passed.

Tool or reviewer findings entering implementation use the existing
[tool-finding-report](../skills/tool-finding-report.md) route when its condition
applies. A verified prompt/handoff gap is corrected before the next affected
handoff; preserve the existing runtime-feedback evidence instead of inventing
a second feedback schema. Optional rejection prediction remains
[optional](../COMMUNICATION_PROTOCOL.md#optional-rejection-prediction).

For an experiment report, read
[experiment report style](../../documents/experiments/experiment-report-style.md).
Ordinary task/Issue/review reports use
[result reporting](ROOT_DELIVERY.md#result-reporting). Research review uses its
selected critical/report/perspective owners; a generic report does not activate
experiment procedures. Performance claims retain separate correctness and
measured-performance evidence, planned comparisons, raw results, interpretation,
and scope. Requested generic JAX export/native paths retain producer and
consumer/runtime evidence; neither is inferred from unrelated successful checks.

## 7. Closeout

Use [Completion Readiness](#completion-readiness) for the selected route. Read
[Coordination closeout](#coordination-closeout) only for a coordination run.

## Completion Readiness

For either execution route, compare the current result and evidence against the
whole agreed deliverable before a terminal response. Use the existing task/Issue
record or selected run state; this adds no checklist artifact or terminal checker.

When a required result is missing, perform its next authorized owning action in
the same task, then reassess the affected evidence. A defect returns to repair;
unmigrated consumers or remaining retired code return to implementation; an unrun
check goes to the selected validation route; missing publication/readback goes to
the delivery owner. Follow pending checks through their existing wait/readback
route. A partial test pass, checkpoint, commit, draft PR, status label, or written
remaining-work list is progress, not a reason to return control to the user.
Recording a gap does not discharge it or require another request to continue.

For a selected child route, a child return establishes only its assigned unit and
evidence. The parent verifies that unit, integrates it, and continues remaining
required work; it does not turn child completion or a blocked child into overall
completion. Delegate or repair through the already authorized route, retaining
user-guided parent ownership. A bounded route has no child return to interpret.
The user's explicit step boundary defines that step's deliverable; do not expand
it to the entire project or wait for unrelated work.

Return a completion result only when the selected bounded evidence or coordination
`task_close.py` result establishes all required outcomes on the final source.
If the user explicitly requests pause/handoff, preserve that boundary. Otherwise,
an incomplete blocker handoff requires evidence that the next required operations
cannot proceed under current authority, safety, or available execution routes,
and that independent actionable required work has been completed. Identify each
blocked property, actual failed operation or authoritative restriction, evidence,
and the specific owner/action that can unblock it. A generic environment concern,
untried available route, task length, or self-chosen checkpoint is not such evidence.
Keep blocked status distinct from completion; preserve safety and rerun limits
without bypasses, speculative environment repair, or repeated unchanged attempts.

Before either result, apply
[reader-facing writing](ROOT_DELIVERY.md#reader-facing-writing) and
[result reporting](ROOT_DELIVERY.md#result-reporting). Issue-backed work receives
comparable rationale, results, limitations, and exact PR/head references on the
Issue. Review-only/no-change work retains its result and source-backed rationale.

## Coordination closeout

For the selected coordination run, pass the existing run evidence through its
closeout owner. `task_close.py` remains the sole coordination terminal predicate;
this owner does not restate its artifact fields or create another checklist.
Keep source/config/schema/fixtures/documentation/tool entrypoints needed by the
runnable commit together under [Branch Scope](../../documents/operations/BRANCH_SCOPE.md).

For selected commit/push operations, record `commit_created` and `push_completed`
as `yes`; unselected operations use the schema's `not_applicable` with the reason.
A missing or failed selected operation remains incomplete. Preserve exact remote
head/tree and post-integration evidence. Creator-owned temporary resources need
their exact identity and absence readback through the cleanup owner before terminal
closeout, preserving unrelated/user-owned resources.

`review_findings_integrated=yes` requires intent-preserving disposition of accepted
findings and authorized withdrawal/replacement/escalation for any discarded slice.
Keep selected review post-fix evidence and required inactive dispositions in the
same run record. The terminal owner consumes canonical tree-head, subagent, log,
evaluation, and coverage evidence under their actual activation conditions.

When behavior feedback/evaluation is selected, update the existing
`workflow_monitoring.md` signals, interventions, decisions, and protocol feedback
with their real outcomes. `--closeout-token-preset` only records established facts;
it does not replace formatter/check, dependency, review, or finding evidence.
An activated evaluation uses `evaluate_agent_run.py` and its behavior manifest;
only its actual result and resolved feedback establish evaluation completion.
Reuse [agent-learning](../skills/agent-learning.md#reader-map) for private knowledge
or behavior-learning decisions. Public failed verification stays in the saved topic
record. A standalone memo save does not activate behavior evaluation.

Keep the selected run's schedule and execution trail current, settle applicable
log-derived avoidances at their owner, and retain required experiment/performance
comparisons and scope-limited claims. Publish actual results through the existing
reporting owner rather than a second closeout checklist or approval gate.
