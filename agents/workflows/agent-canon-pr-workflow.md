# AgentCanon Source PR Workflow
<!--
@dependency-start
contract workflow
responsibility Owns exact AgentCanon source candidate review, GitHub PR CAS, merge, and publication readback.
upstream design ../../documents/agent-canon-update-route.md owns the end-to-end source-to-parent transaction.
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns lifecycle and PR topology schemas.
upstream implementation ../../tools/agent_tools/publication_integrator.py owns candidate CAS and publication authority.
upstream implementation ../../tools/agent_tools/github_publish.py adapts verified GitHub remote and PR operations.
upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns the one source PR gate invocation.
upstream design ../skills/code-visualization.md owns visualization source-publication policy.
upstream implementation ../../tools/agent_tools/visualization_contract.py owns typed visualization coverage evidence.
downstream design pr-queue-cleanup-workflow.md consumes source publication readback.
downstream design ../skills/pr-processing.md consumes PullRequestLifecycle and queue receipts.
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py validates workflow dependency edges.
@dependency-end
-->

This document owns the source PR lane only. The front door and full transaction
are `tools/update_agent_canon.sh` and
`documents/agent-canon-update-route.md`. Parent pin/root projection is a later
consumer and cannot begin here.

## Reader Map

- Read `Candidate Sequence` for source freeze/review/CAS ordering.
- Read `PullRequestLifecycle` for user/fork/contributor and permission handling.
- Read `Publication` for merge/readback and queue handoff.
- Machine schemas live only in `update_lifecycle_contract.py`; this workflow
  names their use and does not define alternate records.

## Specialized Owner Prerequisites

When `code-visualization` owns the source change, its sole public owner and
`visualization_contract.py` supply the exact independent review, route,
coverage, post-format readback, formatter, and producer-checker evidence before
source merge. After merge, that owner executes its canonical source-main
readback gate against every merged path. This workflow consumes the typed
result and does not restate its schema or omission/granularity policy. The
isolated visualization route records `parent_pin_update=forbidden` and does not
modify a parent checkout or pin.

## Source And Branch Ownership

- Canonical source is the standalone AgentCanon clone. A parent submodule
  worktree may be a working copy but the parent is not a source owner.
- Source branch names use `canon/<topic>-YYYYMMDD`.
- Reuse the current branch/lifecycle while its immutable identity and push
  authority remain valid. A closed head, conflict, identity drift, or unrelated
  owner surface creates an explicitly linked successor.
- Root projection views, parent gitlinks, unknown shared state, and upstream
  Materializer implementation are not edited in the source PR lane.

## Candidate Sequence

The only valid append-only order is:

`SourceMainRebindReceipt -> CandidateFreezeReceipt ->
CandidateReviewReceipt -> CandidateCasReceipt -> PullRequestLifecycle open ->
source merge -> PublicationReadbackReceipt/source-main readback`.

1. Read `origin/main` immediately before freeze and record immutable old/new
   base, transaction, snapshot, input, and evidence identity. Later fields are
   absent from this pre-freeze record.
1. Freeze exact candidate commit/tree and append the rebind predecessor.
1. Obtain one independent exact-SHA/tree review. APPROVE binds the same
   candidate; REVISE repairs the same context and appends a new review receipt.
1. CAS against the exact `SourceMainRebindReceipt` new origin/main commit/tree.
   G3 consumes G1/G2 evidence and proves repository, ref, fork/contributor,
   permission, review, and expected-old identity once.
1. Push and PR publication consume that G3 receipt. They do not repeat local
   candidate/tree verification.

Non-sequential predecessor, stale rebind, candidate/tree mismatch, or moved
base fails closed. Changed immutable input requires a successor transaction.

## PullRequestLifecycle

`PullRequestLifecycle` is the only PR state machine. Its discriminator is
`user|fork|contributor`; remote, base, head, fork, and permission identities are
immutable in one record.

- `permission_state=unknown|verified_false` prohibits push, PR mutation, and
  merge. Only verified remote/API evidence with `verified_true` grants the
  relevant authority.
- Draft, ready, changes-requested, and external-review transitions retain PR
  Essence and review history.
- Contributor records additionally retain exact contributor commit/tree/diff.
- Closed head is recorded without inventing a successor.
- Multiple verified remotes block publication until one remote is explicitly
  selected with fresh evidence.
- Conflict or immutable drift enters `conflict_successor` and retains Essence,
  reviews, and contributor diff in the linked successor.

PR Essence always records the problem / user request and design intent, plus
canonical owner, behavior or contract delta, and evidence route. It is preserved
in the run-local PR
body artifact and remote PR body.

## GitHub Adapter Boundary

`github_publish.py` is an internal adapter selected by the update transaction.
It verifies `gh` repository identity against the selected Git remote and reads
viewer permission evidence. `publish-pr` materializes candidate/base/head and
G3 once, reuses them for branch push and PR creation/update, then reads the PR
head/base/review state back. `checks` consumes G3 and, after publication, G5;
it does not create another candidate verdict.

Push authority is never inferred from authentication success, branch name,
repository naming, PR context, or a configured URL. Literal URL push and
multiple-remote guessing are invalid routes.

Standalone direct branch transport is outside the source PR publication gate:
it verifies remote identity/permission, requires a named current branch,
captures local commit/tree, pushes `<commit-sha>:refs/heads/<branch>`, reads
back the exact SHA with `git ls-remote`, and requires branch/HEAD/tree
invariance. It does not generate or claim G1/G2/G3 or PR lifecycle evidence.
When a sealed packet is supplied, candidate matching is retained; PR mutation
and merge remain packet/G1/G2/G3-bound. CI fresh-clone fixtures are
bootstrap/update evidence, not ordinary publication evidence.

## Source PR Gate

`.github/workflows/agent-canon-static-gates.yml` runs only for the PR candidate
(plus explicit manual dispatch). It invokes `check_agent_canon_pr.sh` once.
Branch push and merged-main push do not rerun the same source candidate gate.

`check_agent_canon_pr.sh` consumes G1, runs its static/source PR checks once,
then invokes `check_agent_canon_pr.py` to materialize G2 from those exact
passing checks. G3 is materialized afterward by the GitHub publication owner;
tests consume the production G2 owner and do not claim its owner identity.
Runtime alignment, prompt/eval, convention, skill-command, GitHub workflow,
dependency, docs, and quick-CI work are not called through a second standalone
loop in the same run.

The upstream Materializer hook/archive hot-path defect remains an external
dependency. This workflow records its evidence/blocker and does not implement a
second report/archive materializer.

## Publication

1. `publication_integrator.py` verifies expected-old CAS and publishes the
   approved candidate through the selected PR merge authority.
1. Merge/API readback must authoritatively return PR number, post-merge base-ref
   identity, frozen head identity, merge-CAS base commit/tree from the merge
   commit parent, and merge commit/tree. The merge-CAS base must equal the
   rebind/CAS/lifecycle base. The reviewed candidate remains a separate
   immutable head identity; caller-supplied merge identity is invalid.
1. A distinct post-merge source-main readback proves `origin/main` equals the
   authoritative publication merge commit/tree and materializes G5 publication
   evidence. It is not the pre-freeze rebind receipt.
1. The source lane emits one accepted QueueReceipt and one pending frontier.
   Retry of the same input reuses the receipt.
1. Source PR completion hands off to
   `pr-queue-cleanup-workflow.md`; it never moves the parent pin directly.

## Completion Conditions

- exact rebind/freeze/review/CAS predecessor chain is valid;
- one independent exact-candidate APPROVE exists;
- G1-G3 and source PR CI pass for the same RecordBinding;
- immutable PullRequestLifecycle and permission authority pass;
- expected-old merge CAS passes;
- source-main publication readback matches the authoritative merge commit/tree;
- PR Essence, reviews, and contributor diff where applicable are retained;
- accepted QueueReceipt and pending DependencyFrontier are materialized;
- source/reviewer/PR descendants have durable handback, are closed, and their
  reservations are released;
- parent projection remains untouched until frontier acceptance.

## Prohibited Routes

- editing a parent/root projection as source;
- compatibility branch, wrapper, subtree, or snapshot routes;
- assumed permission or inferred remote selection;
- separate push, PR, checks, and main-push candidate/tree verdicts;
- merging a stale or unreviewed candidate;
- parent pin/root sync before accepted frontier;
- cleanup before remote readback or prose-only agent closeout.
