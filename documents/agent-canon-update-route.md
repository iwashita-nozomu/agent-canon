<!--
@dependency-start
contract reference
responsibility Owns the canonical AgentCanon source-to-parent update transaction and namespace boundaries.
upstream design ../agents/skills/agent-orchestration.md owns Decision Sufficiency policy.
upstream design ../agents/skills/structure-refactor.md owns final-structure-first scope formation.
upstream implementation ../tools/agent_tools/update_lifecycle_contract.py owns lifecycle schemas and transition guards.
downstream implementation ../tools/update_agent_canon.sh executes source rebind, queue/frontier, and parent-projection guards.
downstream implementation ../tools/agent_tools/publication_integrator.py owns source publication CAS/readback.
downstream implementation ../tools/agent_tools/github_publish.py adapts immutable GitHub PR topology.
downstream design ../agents/workflows/agent-canon-pr-workflow.md owns source PR operations.
downstream design ../agents/workflows/pr-queue-cleanup-workflow.md owns projection and cleanup ordering.
@dependency-end
-->

# AgentCanon Update Route

## Front Door And Reader Map

`tools/update_agent_canon.sh` is the single user entrypoint. Read this document
for route meaning and `tools/agent_tools/update_lifecycle_contract.py` for exact
machine schemas. Skills, README files, CI adapters, and parent views link here;
they do not restate the transaction.

The standalone AgentCanon clone is the source owner. A template or derived
repository is a parent projection consumer and never becomes a second source
namespace.

## Owner Namespace

| Surface | Canonical location | Responsibility |
| --- | --- | --- |
| source contract | `tools/agent_tools/update_lifecycle_contract.py` | schemas, identities, guards, receipt materializers |
| source implementation | clone-root `tools/`, `agents/`, `documents/`, `.github/`, `.codex/`, `evidence/`, `tests/`, `rust/` | reviewed product source |
| runtime state | `.agent-canon/update-lifecycle/state/` | resumable transaction pointer and typed GitHub/source-publication packets; never source canon |
| generated evidence | `reports/agents/<run-id>/` and `.agent-canon/update-lifecycle/evidence/` | immutable receipts, timings, review and readback evidence |
| projection queue | `.agent-canon/update-lifecycle/projection-queue/` | accepted QueueReceipt and pending/accepted DependencyFrontier |
| parent projection | parent `vendor/agent-canon` gitlink and AgentCanon-owned root views | downstream view after frontier acceptance only |

Unknown shared state is outside the task-owned namespace and remains unchanged.
There is no legacy subtree, snapshot, wrapper, or alternate owner route.

## Authoritative Transaction

1. Import the owner-produced `DecisionSufficiencyPacket`. When every plausible
   `h in H` selects the same owner/edit/validation tuple, begin execution and
   reject additional zero-value investigation.
1. Consume the final-structure-first contract from
   `agents/skills/structure-refactor.md#Pre-Task Structure Repair Contract` to
   fix the target owner graph and namespace. Once that graph is coherent,
   implementation is the immediate main transition; no update-specific survey,
   precautionary preflight, or intermediate validation step may intervene.
1. Implement the complete source mechanisms and generated views under that
   fixed graph. `UpdateTransaction` and `Snapshot` record resumable progress;
   preparation or generation labels are internal state, not separate route
   gates. Resume at `first_missing_checkpoint`, and return a passed same-input
   receipt with replay timing.
1. Validate the completed source transaction afterward: G1 proves source
   correctness once, and G2 consumes G1 to prove generated completeness once.
1. Before candidate freeze, read `origin/main` and materialize the immutable
   `SourceMainRebindReceipt`. Append, without mutating it:
   `CandidateFreezeReceipt -> CandidateReviewReceipt -> CandidateCasReceipt`.
1. G3 binds immutable remote/base/head/fork/permission identity and the exact
   candidate/tree. `PullRequestLifecycle` carries PR Essence, reviews, and
   contributor diff through draft/ready/review/closed/conflict states. Only
   verified-true permission permits publication.
1. Merge the source PR by expected-old CAS and perform a distinct source-main
   publication readback. Push, PR, and checks reuse the same G3 tree identity;
   they do not independently prove it again.
1. Enqueue exactly one accepted `QueueReceipt` keyed by
   `(source_namespace,candidate_sha,tree_sha,input_digest)`. Create a pending
   `DependencyFrontier` with ordered oracle `#388 -> #389 -> current`.
   The post-readback state machine materializes
   `source-publication-ready.json`; the existing `latest` entry consumes it and
   internally appends queue, frontier acceptance, and G4 evidence.
1. Accept the frontier only when source-main equals the current candidate,
   QueueReceipt is accepted, and all predecessor publication evidence is
   present and ordered. Pending/failed frontier records prohibit parent work.
1. G4 permits one parent pin/root projection. Parent-owned validation and
   remote CI run once, then G5 proves exact remote publication readback. Parent
   consumers trust G1-G3 receipts and do not repeat those invariants.
1. After G5, materialize DurableHandback, close every descendant, release every
   reservation, clean only task-owned temp/cache, prove unknown shared state
   unchanged, pass G6, and execute the canonical terminal `close_agent`
   ToolCall token.

Identity mismatch or closed-head conflict creates an explicitly linked
successor; it never mutates the old transaction. Retry is driven by typed state,
not elapsed time, line count, read count, retry count, or check count.

## Canonical Six Boundaries

| Gate | Owner invariant | Downstream trust |
| --- | --- | --- |
| G1 | source correctness | G2/publication eligibility consume receipt |
| G2 | generated completeness | PR CI consumes receipt |
| G3 | PR identity, permission, review, CAS | source merge and queue consume receipt |
| G4 | accepted frontier and parent projection integrity | parent publication consumes receipt |
| G5 | exact remote publication readback | cleanup may begin |
| G6 | handback, descendants, reservations, cleanup, close token | terminal auditor consumes receipt |

Each invariant has one canonical gate. Downstream tools validate receipt
identity and ordering only; they do not rerun the owned check.

## Command Responsibilities

| Entry | Responsibility |
| --- | --- |
| `tools/update_agent_canon.sh plan` | optional read-only projection only when its result can change the owner/structure decision; never a required preflight |
| `tools/update_agent_canon.sh latest` | standalone source-main rebind; after typed publication readback, internal queue/frontier advance; in a parent, accepted-frontier projection |
| `tools/update_agent_canon.sh apply` | strict clean source rebind or accepted parent projection |
| `tools/update_agent_canon.sh merge-main-into-current` | clean standalone/source-branch rebind |
| `tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` | task-dirt-preserving source rebind |
| `tools/ci/check_agent_canon_pr.sh` | consume G1-G3 and run the one source PR gate |
| `tools/ci/check_agent_canon_latest.sh` | consume G4-G5 without a second source-main check |

## Failure And Cleanup Semantics

- Unknown or false push permission: refuse mutation.
- Rebind/freeze/review/CAS predecessor mismatch: fail the current transaction;
  changed identity requires a successor.
- Duplicate or reordered `#388/#389/current` evidence: refuse frontier
  acceptance.
- Parent projection before accepted frontier: fail closed.
- Remote readback mismatch: no cleanup; retry the same identity only when the
  failure is typed transient.
- Completed-but-open or unknown descendant, reservation leak, malformed token,
  or cleanup before G5: G6 failure.
- Cleanup deletes only enumerated task-owned paths after readback. Unknown
  shared state must have equal before/after digests and unchanged evidence.
