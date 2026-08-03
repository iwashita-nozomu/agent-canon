<!--
@dependency-start
contract reference
responsibility Owns the canonical AgentCanon source-to-parent update transaction and namespace boundaries.
upstream design ../../agents/skills/agent-orchestration.md owns Decision Sufficiency policy.
upstream design ../../agents/skills/structure-refactor.md owns final-structure-first scope formation.
upstream design ../rule/dependency-module-changes.md owns generic dependency source-clone and clean-projection policy.
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns lifecycle schemas and transition guards.
downstream implementation ../../tools/update_agent_canon.sh executes source rebind, queue/frontier, and parent-projection guards.
downstream implementation ../../tools/agent_tools/publication_integrator.py owns source publication CAS/readback.
downstream implementation ../../tools/agent_tools/github_publish.py adapts immutable GitHub PR topology.
downstream design ../../agents/workflows/agent-canon-pr-workflow.md owns source PR operations.
downstream design ../../agents/workflows/pr-queue-cleanup-workflow.md owns projection and cleanup ordering.
@dependency-end
-->

# AgentCanon Update Route

## Front Door And Reader Map

`tools/update_agent_canon.sh` is the single user entrypoint. Read this document
for route meaning and `tools/agent_tools/update_lifecycle_contract.py` for exact
machine schemas. Skills, README files, CI adapters, and parent views link here;
they do not restate the transaction.

## Auto-Commit Provenance Boundary

Every mutating route that can stage, checkout, update a submodule, mutate a root
view, park eval logs, or create an automatic sync commit must validate the
existing four Git authority/reason fields and the additional
`AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex>` input before
the first mutation. The evidence digest is the SHA-256 of the exact bytes of
the user request record or canonical workflow authorization packet. Missing,
uppercase, malformed, or fallback evidence is rejected; there is no actor or
authority compatibility input.

`tools/sync_agent_canon.sh::commit_sync_paths_if_needed` owns automatic sync
commits. It always sets Author and Committer to
`AgentCanon Sync Automation <agent-canon-sync@automation.invalid>` and emits
formal `AgentCanon-*` trailers for the automation actor, validated authority
source, destructive authority, request evidence, remote, update method, and
prefix. The trailers must remain readable by `git interpret-trailers --parse`.

The parent repository has two distinct AgentCanon states. Parent pin/root
projection is ready only when `vendor/agent-canon` is clean on named `main` and
its worktree `HEAD` equals the staged index gitlink. Source editing is owned by
a named topic branch in the current `vendor/agent-canon` checkout; `main` is
only the topic-creation starting point. The intended topic branch may carry
committed differences and collision-free uncommitted paths during source update
materialization. A managed workspace clone is a fallback only when another
topic already occupies the parent vendor with dirty state.

The complete parent-state, requested-topic, and dirty-fallback decision is owned
by [`documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table`](../rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
The `latest` update-target branch is not a topic identity; reuse an existing topic
owner or use `AGENT_CANON_TOPIC_SLUG` when an explicit requested topic is needed.

For any dependency source edit, apply
`documents/rule/dependency-module-changes.md`: default route uses the current
`vendor/agent-canon` checkout for direct source work when it is the intended
named topic branch; route to the managed topic workspace clone only when another
active topic owns that checkout, publish there, and then project a clean vendor
pin.

## Update Materialization Acceptance

The local-state block predicate for `plan`, `latest`, `apply`, and
`merge-main-into-current` is exactly:

```text
block := materialization_merge_conflict(
           existing_unresolved_index or virtual_merge_result_conflict
         )
      or unpreservable_materialization_collision(
           local_materialized_paths intersect exact_update_write_set
         )
```

`exact_update_write_set` is empty when the current commit already contains the
remote commit. Otherwise Git computes a virtual merge result with
`merge-tree --write-tree`; the write set is every path whose tree entry differs
between current `HEAD` and that result tree. This includes destinations produced
by Git's rename handling without a second handwritten rename heuristic. An
existing unresolved index or a conflict reported while producing the virtual
result is the independently typed `materialization_merge_conflict` blocker.

Equal paths and file/directory prefix collisions are unpreservable.
`local_materialized_paths` is the union of tracked worktree modifications,
staged changes, conflicted paths, ordinary untracked paths, and ignored
untracked paths. Ignored status changes visibility, not whether Git could
overwrite the materialized path.

A named branch, `ahead` or `diverged` history, parent/worktree pin difference,
and dirty worktree or update-surface status are state evidence, not blockers.
The updater leaves non-colliding local materialized paths in place and uses the
normal Git merge and review flow for committed branch differences. This route
has no clean-tree hard requirement, dirty-path count baseline, stash/reset
transaction, or compatibility materialization route. Parent pin/root projection
eligibility remains the separate clean-`main` contract after source publication.

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
1. Merge the source PR by expected-old CAS. Authoritative PR readback keeps the
   post-merge base ref separate from the merge-parent commit/tree and requires
   that merge-parent identity to equal the rebind/CAS base. A distinct
   source-main publication readback follows. Push, PR, and checks consume one
   sealed G3 authority; post-publication checks additionally consume sealed,
   same-binding G5 evidence.
   Standalone `github_publish.py push` without a packet is reversible branch
   transport only: verified remote identity/permission, named current branch,
   captured local `HEAD`/tree, exact SHA refspec, remote `ls-remote` readback,
   and push-spanning local identity invariance. It does not generate or claim
   G1/G2/G3 or PR lifecycle evidence. Packet-bound push may additionally check
   its sealed candidate identity; `publish-pr`, PR mutation, and merge remain
   sealed packet/G1/G2/G3-bound.
1. Enqueue exactly one accepted `QueueReceipt` keyed by
   `(source_namespace,candidate_sha,tree_sha,input_digest,
   publication_merge_sha,publication_merge_tree)`. Create a pending
   `DependencyFrontier` with ordered oracle `#388 -> #389 -> current`.
   The post-readback state machine materializes
   `source-publication-ready.json`; the existing `latest` entry consumes it and
   internally appends queue, frontier acceptance, and G4 evidence.
1. Accept the frontier only when source-main equals the authoritative
   publication merge commit/tree, QueueReceipt is accepted, and all predecessor
   publication evidence is present and ordered. The reviewed candidate remains
   the immutable PR head identity and is not substituted for the merge result.
   Pending/failed frontier records prohibit parent work.
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
| G2 | generated completeness | G3 consumes the owner-produced receipt |
| G3 | PR identity, permission, review, CAS | source merge and queue consume receipt |
| G4 | accepted frontier and parent projection integrity | parent publication consumes receipt |
| G5 | exact remote publication readback | cleanup may begin |
| G6 | handback, descendants, reservations, cleanup, close token | terminal auditor consumes receipt |

Each invariant has one canonical gate. Downstream tools validate receipt
identity and ordering only; they do not rerun the owned check.

## Command Responsibilities

| Entry | Responsibility |
| --- | --- |
| `tools/update_agent_canon.sh plan` | read-only route and local-state evidence, including the update materialization predicate and exact collision result |
| `tools/update_agent_canon.sh latest` | standalone source-main rebind; in a parent, collision-safe named topic merge or accepted-frontier projection after publication |
| `tools/update_agent_canon.sh apply` | apply the accepted projection while preserving non-colliding local paths in place |
| `tools/update_agent_canon.sh merge-main-into-current` | merge remote main into the current named source branch under the update materialization predicate |
| `tools/ci/check_agent_canon_pr.sh` | consume G1, run the one source PR gate, then invoke the G2 owner |
| `tools/ci/check_agent_canon_pr.py` | materialize/replay G2 from the ordered passing generated-completeness checks |
| `tools/ci/check_agent_canon_latest.sh` | consume G4-G5 without a second source-main check |

## Centralized Template Parent Follow-Up

When a source update changes centralized template owners under source-root
`templates/`, the parent projection packet is incomplete until it records all
of the following:

- removal of the retired parent-root `templates` symlink while preserving
  `vendor/agent-canon/templates/`;
- deletion of parent `experiments/_template/`;
- deletion of only the `_template` entry in the parent project registry;
- deletion of parent docs/tests that only exercise that removed scaffold; and
- regeneration and validation of GitHub Issue/PR projections from
  `vendor/agent-canon/templates/documents/github/`.

The parent registry remains project-owned. AgentCanon source validation uses a
temporary parent-shaped registry fixture and never mutates a source or parent
registry during the template smoke check.

## Failure And Cleanup Semantics

- Unknown or false push permission: refuse mutation.
- Rebind/freeze/review/CAS predecessor mismatch: fail the current transaction;
  changed identity requires a successor.
- Duplicate or reordered `#388/#389/current` evidence: refuse frontier
  acceptance.
- Parent projection before accepted frontier: fail closed.
- Local uncommitted path colliding with the exact update write set: preserve the
  checkout and refuse materialization with the colliding path.
- Existing or newly produced unresolved merge conflict: preserve the merge state
  for explicit resolution and refuse further materialization.
- Remote readback mismatch: no cleanup; retry the same identity only when the
  failure is typed transient.
- Link-root/check coverage is explicitly limited to the current parent checkoutの
  pin/root projection readiness; do not use them to assert remote branch
  ownership, other-workspace clone status, or PR lifecycle invariants.
- Completed-but-open or unknown descendant, reservation leak, malformed token,
  or cleanup before G5: G6 failure.
- Cleanup deletes only enumerated task-owned paths after readback. Unknown
  shared state must have equal before/after digests and unchanged evidence.
