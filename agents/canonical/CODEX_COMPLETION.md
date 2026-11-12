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
| Completing coordinated work | [Completion Review](#completion-review) and [Coordinated delivery](#coordinated-delivery) |
| Reporting or handing off the result | [Completion Readiness](#completion-readiness) |

## Completion Bar

Account for all active request clauses, the complete affected responsibility unit,
selected validation, activated review, and authorized publication/cleanup. Preserve
the agreed target and required input domain rather than calling an incomplete
slice complete. Each material result has its actual operation and evidence.
Necessary path/link presence, forbidden legacy-path absence, and sufficient
behavior are different claims; select the evidence the changed contract requires.
For changed code, use the [implementation and deletion review](CODEX_IMPLEMENTATION.md#5-implementation)
to confirm actual removal and caller migration from the final diff and references.
A deletion plan or passing replacement tests alone does not close that work.
After a repair detour, distinguish cause-side changes/checks from the requested
target's resulting behavior and acceptance evidence. If its interrupted operation
is still unfinished, use the retained
[return point](CODEX_IMPLEMENTATION.md#return-from-a-repair-detour). A target that
needs no further edit still requires its selected acceptance evidence; reuse valid
results and preserve explicit validation holds rather than adding a new check.

Review source against equations, specifications, invariants, and assumptions when
present. Treat review suggestions as hypotheses: settle them against current
source, reachable behavior, and a witness or sound analysis. Repair accepted
in-scope findings while preserving intent; record verified rejection, escalation,
and unresolved claims with their effects on completion. Recheck only changed or
invalidated evidence. When Local Capability Priority was selected, retain its
[capability decision](../skills/agent-orchestration.md#local-capability-priority).

An implemented, published, or handed-off result is not automatically verified or
applied. An unmet requirement returns to its next owning action through
[Completion Readiness](#completion-readiness), rather than becoming a terminal
response with a remaining-work list. Unrelated checks and other Issues do not
become completion prerequisites.

## Bounded delivery

For `bounded_fast_path`, use the current conversation and actual diff/results.
Report the final checks and an activated review when one was selected. No work
ledger, scope table, or per-commit evidence record is required.
If the request includes base integration or publication, carry its current-base
and authorized remote readback. Clean up only task-owned resources created by
the selected operations. Decide commit and push under
[delivery ownership](ROOT_DELIVERY.md#commit-and-push-decisions).

The selected results are the evidence. A concrete new
coordination need returns only that changed decision to the route owner; labels,
links, and report length do not initiate a route change.

## Completion Review

Compare the agreed outcome with the actual diff, selected validation and activated
review results. Finish authorized publication and synchronization with their native
owner, then read back the resulting state. Preserve unknown state and clean up
task-owned resources when their use ends. No custom closeout gate or run bundle
is created.

## 6. Validation

Use the changed contract's selected profile/check matrix and the common
[formatting and verification boundary](../../ROOT_AGENTS.md#validation-routing).
静的解析、読み取り確認、docs / targeted tests / agent checks を、変更契約と残るリスクから選びます。
Report the final-source formatter/check and selected validation results;
later edits or integration invalidate only the affected evidence. Separate CI,
format, and synthetic checker-retest paths are not extra completion predicates.

For dependency/header changes, use the existing source-derived checks and relevant
downstream review. Select a whole-repository dependency review only when the
changed contract or explicit request requires it. Shared canon, Large Delivery,
and high-risk labels alone do not request every repository check.

After failed verification, use the actual output to distinguish observation,
cause, input assumptions, and required API behavior before deciding a repair.
Keep the diagnosis and next action in the conversation. No failure-topic file,
classification ledger, or per-attempt status record is required. Unrun checks
remain unverified.

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
[Coordinated delivery](#coordinated-delivery) when integrating child work.

## Completion Readiness

For either execution route, compare the current result and evidence against the
whole agreed deliverable before a terminal response. Use the current context,
actual diff, and available results; no completion ledger is required.

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

Return a completion result only when the selected evidence establishes all
required outcomes on the final source.
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

## Coordinated delivery

Integrate selected child work and accepted review findings, then check the final
diff and actual validation results. Keep source, fixtures, documentation, and
entrypoints needed by the runnable commit together under
[Branch Scope](../../documents/operations/BRANCH_SCOPE.md). Read back authorized
publication and clean up task-owned temporary resources, preserving unknown state.

Selected Eval and archival operations retain their existing owners. Report their
actual results when requested; they do not require new run bundles or progress files.
