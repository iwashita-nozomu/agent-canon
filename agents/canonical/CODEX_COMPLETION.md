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

Account for the full agreed target, its required input domain, and each requested
result through its actual operation and evidence.
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

## Bounded delivery

For `bounded_fast_path`, use the current conversation and actual diff/results.
If the request includes integration or publication, include the current base
and remote readback. Use [commit and push decisions](ROOT_DELIVERY.md#commit-and-push-decisions).
A new coordination need returns to the route owner.

## Completion Review

Compare the agreed outcome with the actual diff, selected validation and activated
review results. For child work, follow [Coordinated delivery](#coordinated-delivery).

## 6. Validation

Use the changed contract's selected profile/check matrix and the common
[formatting and verification boundary](../../ROOT_AGENTS.md#validation-routing).
静的解析、読み取り確認、docs / targeted tests / agent checks を、変更契約と残るリスクから選びます。
Report the final-source formatter/check and selected validation results.

For dependency/header changes, use the existing source-derived checks and relevant
downstream review. Select a whole-repository dependency review when the changed
contract or explicit request requires it.

For a failed or unverified property, use the
[common completion rule](../../ROOT_AGENTS.md#task-entry) to reconsider the
assumptions and select evidence for the requested behavior.

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

Match the requested outcomes to the actual artifacts, diff, and validation.
Use the [common completion rule](../../ROOT_AGENTS.md#task-entry) for remaining
work or a concrete blocker. The parent verifies integrated child work against
the same request. Respect the user's requested pause or handoff boundary.

Use [result reporting](ROOT_DELIVERY.md#result-reporting) to communicate the
completed scope and any remaining blocker.

## Coordinated delivery

Integrate selected child work and accepted review findings, then check the final
diff and actual validation results. Keep source, fixtures, documentation, and
entrypoints needed by the runnable commit together under
[Branch Scope](../../documents/operations/BRANCH_SCOPE.md). Read back authorized
publication and clean up task-owned temporary resources, preserving unknown state.

Report actual results from the selected Eval and archive owners.
