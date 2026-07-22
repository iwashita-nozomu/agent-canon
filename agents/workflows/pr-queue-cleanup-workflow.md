# AgentCanon Projection Queue And Cleanup Workflow

<!--
@dependency-start
contract workflow
responsibility Owns ordered source projection, parent frontier consumption, and task-owned cleanup after remote readback.
upstream design ../workflows/agent-canon-pr-workflow.md owns source PR merge and publication readback.
upstream design ../../documents/agent-canon-update-route.md owns the end-to-end transaction.
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns QueueReceipt, DependencyFrontier, CleanupProof, and close token schemas.
upstream implementation ../../tools/update_agent_canon.sh emits queue/frontier receipts and blocks early parent projection.
upstream implementation ../../tools/agent_tools/report_artifact_checks.py remains the upstream completion Materializer.
downstream implementation ../../tools/agent_tools/task_close.py consumes G1-G6 and terminal cleanup evidence.
downstream implementation ../../tools/ci/check_agent_canon_latest.sh consumes G4/G5 receipts.
@dependency-end
-->

Use this workflow after exact source-main publication readback. It owns the
boundary between source merge and parent projection, then the boundary between
remote readback and cleanup. It does not grant mutation authority for an
unrelated PR or unknown shared state.

## Parent Projection Boundary

Parent projection means the downstream `vendor/agent-canon` pin, AgentCanon-
owned root views, parent validation, parent remote CI, merge, and readback. It
is not source canon. It begins only from an accepted `DependencyFrontier` plus
the current source publication readback.

Before acceptance, `parent_projection_evidence_ref` is null and no pin/root
sync is permitted. The parent is monitor/integrator: it consumes G1-G3 and does
not rerun source correctness, generated completeness, review, or source PR CAS.

## Cleanup Order

1. Source merge/readback emits one accepted QueueReceipt under the exact
   `(source_namespace,candidate_sha,tree_sha,input_digest)` key. Same-input
   replay returns that receipt and does not enqueue twice.
1. Materialize a pending DependencyFrontier whose ordered predecessor oracle is
   `source_pr:#388 -> source_pr:#389 -> transaction:<current_transaction_id>`.
   Pending acceptance evidence is null.
1. Append accepted frontier evidence only after exact source-main candidate
   readback, accepted queue identity, immutable rebind evidence, and dependency
   checks pass. Accepted state links to the prior pending evidence record.
1. Perform one parent pin/root projection. Run only parent-owned validation and
   remote CI, merge by expected-old authority, and read the parent publication
   back. Materialize G4 then G5.
1. After G5, write DurableHandback for source/reviewer/PR/pin agents. Close every
   declared descendant immediately after its durable handback and retain each
   terminal receipt.
1. Release every reservation and retain release receipts. A completed-but-open
   child, unknown descendant, or active reservation is a closeout failure.
1. Materialize CleanupProof from enumerated task-owned temp/cache paths,
   before/after task state, and equal unknown-shared-state digests. Delete only
   those task-owned paths.
1. Materialize G6 from G1-G5, handback, descendant, reservation, and cleanup
   evidence, then materialize and execute the canonical terminal `close_agent`
   ToolCall token.

The upstream report/archive Materializer and hook hot path are dependencies,
not implementations in this workflow. A Materializer defect is recorded as an
upstream blocker; no second archive/materialization loop is added here.

## Authority

- Source PR merge, parent PR mutation, ready/merge, and branch deletion require
  current-task authority or tracked maintainer policy for that exact action.
- Authentication success is not push or merge permission evidence.
- Parent projection authority does not authorize source mutation or cleanup of
  unknown state.
- A successor transaction requires changed immutable input or an explicit
  closed/conflict lifecycle transition.

## Stop Conditions

Stop the current transition with its typed failure and preserve all prior
receipts when:

- QueueReceipt identity mismatches or an accepted key would be re-enqueued;
- `#388/#389/current` evidence is missing, duplicated, or reordered;
- source-main readback does not equal the current candidate/tree;
- frontier is pending/failed or lacks its preceding pending evidence;
- parent pin/root projection is attempted before acceptance;
- parent publication readback mismatches the approved projection;
- durable handback is absent;
- a descendant is completed but open or is not declared;
- a reservation remains active;
- cleanup is attempted before G5 or names a non-task-owned path;
- unknown shared state changes;
- any G1-G6 evidence identity or terminal ToolCall binding is malformed.

No stop condition is based on timeout, retry count, file count, line count,
search count, or check count. A typed transient failure may retry the same
identity; changed input creates a successor.

## Completion Evidence

- accepted QueueReceipt and pending/accepted frontier pair;
- ordered `#388 -> #389 -> current` publication evidence;
- G4 parent projection and G5 remote readback receipts;
- parent PR/merge/readback identity;
- DurableHandback and exact descendant terminal ledger;
- reservation release ledger;
- CleanupProof with task-owned paths and unchanged shared-state evidence;
- G1-G6 evidence refs and terminal `CloseAgentToolCall` token ID.
