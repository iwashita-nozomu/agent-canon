# AgentCanon Source PR Workflow
<!--
@dependency-start
contract workflow
responsibility Owns exact AgentCanon source candidate review, GitHub PR CAS, merge, and publication readback.
upstream design ../../documents/agent-canon/agent-canon-update-route.md owns the end-to-end source-to-parent transaction.
upstream design ../../documents/agent-canon/source-publication-parent-handoff.md owns the source packet handoff boundary.
upstream design ../../documents/design/source-owned-dependency-validation.md owns source review authority and PR receipt states.
upstream design ../../documents/design/dependency-manifest-design.md owns manifest DSL and explicit graph-analysis projection.
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns lifecycle and PR topology schemas.
upstream implementation ../../tools/agent_tools/source_projection_handoff.py materializes the sole parent handoff packet.
upstream implementation ../../tools/agent_tools/publication_integrator.py owns candidate CAS and publication authority.
upstream implementation ../../tools/agent_tools/github_publish.py adapts verified GitHub remote and PR operations.
upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns the one source PR gate invocation.
upstream implementation ../../tools/ci/pr_gate_receipt.py owns the source/skipped receipt schema consumed by quick CI.
upstream design ../skills/code-visualization.md owns visualization source-publication policy.
upstream implementation ../../tools/agent_tools/visualization_contract.py owns typed visualization coverage evidence.
downstream design pr-queue-cleanup-workflow.md consumes source publication readback.
downstream design ../skills/pr-processing.md consumes PullRequestLifecycle and queue receipts.
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py validates workflow dependency edges.
@dependency-end
-->

This document owns the source PR lane only. The front door and full transaction
are `tools/update_agent_canon.sh` and
`documents/agent-canon/agent-canon-update-route.md`. Parent pin/root projection is a later
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

- Canonical source is the parent repository `vendor/agent-canon` on a
  topic-named branch. A managed `workspace/<topic>/agent-canon` clone is a
  fallback only when that parent vendor checkout is already occupied by another
  topic's dirty state.
- Parent vendor state and requested-topic selection follow the
  [`AgentCanon parent state decision table`](../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
  The `latest` update-target branch is never a topic slug.
- `vendor/agent-canon` が `main` のみの状態のまま source 編集へ進まない。まず
  topic branch を用意して同一トピックの source lane を再開する。
- Parent pin/root projection is a separate state and passes only with clean
  `main` plus `worktree HEAD == staged index gitlink`; it does not authorize
  source editing. The intended named topic branch is the source owner; dirty,
  ahead, and diverged state are evidence, while virtual/existing merge conflict
  and unpreservable materialization collision are independently typed blockers.
- Source branch names use `canon/<topic>-YYYYMMDD`.
- Reuse the current branch/lifecycle while its immutable identity and push
  authority remain valid. A closed head, conflict, identity drift, or unrelated
  owner surface creates an explicitly linked successor.
- `workspace/<topic>/agent-canon` standalone clone created for a dirty
  `vendor/agent-canon` fallback route is allowed only for PR-source
  materialization. It must be deleted at the point where PR creation/update is
  performed with `local commit == pushed commit == PR head` and readback of that
  PR head succeeds. After successful readback, the local clone is deleted.
- If unmaterialized diff remains, deletion is prohibited until those changes are
  materialized to the same PR and the PR head readback confirms identity.
- After merge/readback, cleanup may consume the same full integrated-commit
  receipt even when the source clone retains local topic commits from a squash
  merge. The integrated commit must be reachable from fetched `origin/main` and be
  a descendant of `topic_base = merge-base(HEAD, origin/main)`. Exact computed path,
  clean/untracked-zero state, and per-path final-tree inclusion/deletion are
  authoritative. When `topic_base..HEAD` has unique commits but no changed paths,
  cleanup additionally requires readback that the local HEAD is retained by a
  fetched remote integrated history or remote topic head; this rejects an old
  same-content commit followed by an unpushed allow-empty commit. Stale or missing
  membership markers are read back as `marker-readback=membership-mismatch` before
  the proof result and do not block cleanup by themselves. Dirty state, URL/branch/
  owner evidence mismatch, a wrong-base integrated commit, missing remote-tip
  evidence, and non-equivalent integrated commits still hold. Once the managed
  child is removed, an empty topic container is removed by that same receipt; no
  re-clone or `prepare` repair is inserted.
- For open PR repair work in this lane, always check out the PR remote head
  branch in the source clone, merge latest `origin/main`, and resolve conflicts.
  Then make a local commit on the same branch, push to that same branch,
  read back the PR head, and delete the local clone after successful readback.
- If the PR is already merged or closed and its head can no longer be updated,
  create a successor topic branch from latest `origin/main`, open a successor PR,
  and continue the normal sequence for publication readback; do not update the
  merged/closed PR.
- Root projection views, parent gitlinks, unknown shared state, and upstream
  Materializer implementation are not edited in the source PR lane.
  Branch/repo match checks (`readback` identity, branch remote matching,
  merge-base invariants, permission evidence) belong to the source PR readback
  owner route and are not duplicated in `link-root`.

## Candidate Sequence

The only valid append-only order is:

`SourceMainRebindReceipt -> CandidateFreezeReceipt -> CandidateReviewReceipt ->
CandidateCasReceipt -> PullRequestLifecycle open -> source merge ->
PublicationReadbackReceipt/source-main readback`.

1. Fetch `origin/main` / read identity immediately before freeze.
1. Merge `origin/main` into the topic branch.
1. Resolve conflicts using explicit ownership intent and dependency-edge
   requirements from the parent scope.
1. Record one local exact candidate commit and freeze both candidate hash and
   tree as `CandidateFreezeReceipt`.
1. Obtain one independent exact-SHA/tree review of the frozen candidate.
   APPROVE binds that exact candidate state; REVISE repairs the same context and
   appends a new review receipt.
1. Record one CAS for the merge context of that frozen reviewed candidate
   (`CandidateCasReceipt`). Base-read-only CAS or base read is not an
   acceptable substitute for merge in this lane.
1. exact reviewed commit push.
1. PR create/update.
1. source merge -> PublicationReadbackReceipt/source-main readback.

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
It verifies `gh` repository identity against the selected Git remote, reads
viewer permission evidence, and binds the current user task, remote/topology,
and exact head/base identities. Ordinary branch transport, PR creation/update,
and check readback use those owner facts and their exact remote/API readback;
they do not require workspace-packet materialization or G1/G2/G3. A sealed
packet may add candidate matching as optional enrichment. Merge remains the
G3-bound operation, and post-publication checks may consume its own G5 readback;
the adapter does not create another candidate verdict.

Push authority is never inferred from authentication success, branch name,
repository naming, PR context, or a configured URL. Literal URL push and
multiple-remote guessing are invalid routes.

Standalone direct branch transport is outside the source PR publication gate:
it verifies remote identity/permission, requires a named current branch,
captures local commit/tree, pushes `<commit-sha>:refs/heads/<branch>`, reads
back the exact SHA with `git ls-remote`, and requires branch/HEAD/tree
invariance. It does not generate or claim G1/G2/G3 or PR lifecycle evidence.
When a sealed packet is supplied, candidate matching is retained as optional
enrichment; PR mutation and check readback still consume current task,
verified remote/permission/topology, and exact identities. Merge remains
G3-bound. CI fresh-clone fixtures are
bootstrap/update evidence, not ordinary publication evidence.

## Source PR Gate

`.github/workflows/agent-canon-static-gates.yml` runs only for the PR candidate
(plus explicit manual dispatch). It invokes `check_agent_canon_pr.sh` once.
Branch push and merged-main push do not rerun the same source candidate gate.

`check_agent_canon_pr.sh` consumes G1, runs its static/source PR checks once,
then invokes `check_agent_canon_pr.py` to materialize G2 from those exact
passing checks. G3 is materialized afterward by the GitHub publication owner;
tests consume the production G2 owner and do not claim its owner identity.
Runtime alignment, convention, skill-command, GitHub workflow, dependency, docs,
and quick-CI work are not called through a second standalone loop in the same
run. AgentCanon development prompt and accumulated eval producers are owned by
the standalone AgentCanon static-gates route only; a derived parent shared gate
does not invoke them or apply their diagnostics to parent-owned documents.

### Parent Gate Necessary Conditions

For `template_or_derived` repositories, the PR gate always requires the
submodule's configured URL, gitlink mode, and pinned commit to be present, and
every changed shared/root projection to pass its existing projection check. A
local parent branch being ahead, behind, diverged, or dirty is preserved as
state and does not fail this gate by itself. An actual materialization collision
remains a blocker in the projection and generated-artifact checks. The gate
does not require the pinned commit to be reachable from the configured remote
or the worktree `HEAD` to equal the staged gitlink; those pin lifecycle checks
belong to the parent pin/root projection route.

Dependency review is source-owned. The selector acquires trusted base/head and
changed-path evidence, then `run_pr_dependency_source_gate.sh` runs the source
scan, format, relation/cycle, and source-derived TSV/DOT projections selected by
the current profile. The normal PR route does not build, query, or read a
persisted graph and does not promote graph completeness into a receipt.
`check_agent_canon_pr.sh` emits `source` when full source review runs and
`skipped` when only the trusted header scan runs. The shared gate never runs
repository project tests, type checks, or lint. A derived parent projects those
checks with `AGENT_CANON_PR_PROJECT_QUALITY=delegated` and owner `parent_ci`;
its parent workflow must expose that owner marker together with the canonical
`make ci` command. The existing workflow checker validates this route by owner
and command semantics, not by a fixed job name. Standalone AgentCanon keeps the
existing `static-gates` shared-surface owner and introduces no repository-wide
project-quality job. The PR script does not add a second workflow parser or
fallback runner.

`tools/bin/agent-canon graph build|status|query|context` and
`run_repo_dependency_review.sh --ensure-graph` remain explicit graph-analysis
capabilities. Their persisted diagnostics and freshness contract are not inputs
to the normal PR source review or receipt consumer. Graph acceptance and
SQLite/database identity remain owned by that explicit analysis route.

GitHub Actions resolves the comparison base from
`pull_request.base.sha` in its trusted event payload. Before normal selection,
`check_agent_canon_pr.sh` invokes `--prepare-ci-base`. The selector first verifies
that the exact event base object and the merge-base history needed for comparison
are already available; that state skips fetch and needs no credential. When a
shallow or incomplete checkout needs fetch, the workflow supplies
`AGENT_CANON_PR_READ_TOKEN: ${{ github.token }}` only to the static-gate step, and
the selector applies it through process-local Git configuration for the exact
event SHA. The credential is not written to checkout or repository Git config,
and `actions/checkout` retains `persist-credentials: false`. Public, private, and
fork PRs use this same trusted event-SHA route. The emitted SHA is supplied as
`--trusted-base-sha`; the selector requires it to equal the event SHA. The normal
local `check_agent_canon_pr.sh` owner reads the verified `origin` `refs/heads/main`
SHA and passes that immutable value through `--trusted-base-sha`; the lower
selector consumes it and does not choose or re-read a comparison base. A missing
remote SHA, base equal to `HEAD`, unresolvable or history-unreachable base, and
failed fetch or diff command produce a typed selector failure; no environment
fallback, parent fallback, or empty-diff success is inferred.

The accepted GitHub publication boundary is a separate owner route: ordinary
branch transport uses non-force fast-forward push plus exact remote readback, and
PR create/update and check readback consume the current user task, verified
remote/permission, and exact head/base identities. Those operations do not
require G1/G2/G3 or workspace-packet materialization. G1-G3 remain candidate
validation and merge authority, not PR-opening, metadata-read, or check-read
authority.

### One-Judgment-Owner Check Handoff

Each check family has one execution owner in a source PR gate. For a derived
parent, the direct AgentCanon check function owns only shared runtime,
convention, skill-command, GitHub workflow, documentation, dependency-header,
and graph checks; it does not run AgentCanon development prompt or accumulated
eval producers, and it never enters a repository project's test/type/lint
route. Standalone AgentCanon owns those eval producers in its existing
`static-gates` job. The standalone static workflow does not add a repository-wide
project-quality job. The selected parent CI route owns derived-project quality
consumers, and the workflow checker validates that route's owner marker and
canonical command.

After the selected dependency review, the PR gate writes a temporary receipt
through `tools/ci/pr_gate_receipt.py`. It contains its owner, root identity,
parent PID, matching `strict_dependency`/`graph` compatibility fields with
status `source` or `skipped`, and selector reason/evidence. The same module
validates the receipt once in the consumer and returns one `status=...` line;
shell callers do not reparse its keys. `prepared` and `scoped` are retired
graph states and fail closed. The receipt protects the shared
checker-to-consumer process handoff; a cryptographic nonce for a hostile local
caller is outside this trust boundary and would not establish that the caller
ran the checker. The selected workflow job is the sole blocking project-quality
consumer, and an invalid or missing receipt supplied to any separate internal
consumer fails closed.

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
1. `source_projection_handoff.py` consumes the exact post-readback
   predecessor records and materializes one immutable source-projection packet
   in the explicit parent owner namespace. That packet is the only
   cross-namespace payload.
1. The canonical `update_agent_canon.sh latest` front door validates remote
   source-main commit/tree and derives QueueReceipt, pending/accepted frontier,
   transaction marker, and G4 in the parent namespace. Retry of the same input
   reuses immutable identities; derived receipt copy is invalid.
1. Source PR completion hands off to
   `pr-queue-cleanup-workflow.md`; it never moves the parent pin directly.

## Completion Conditions

- exact rebind/freeze/review/CAS predecessor chain is valid;
- one independent exact-candidate APPROVE exists;
- G1-G3 and source PR CI pass for the same RecordBinding;
- submodule structure evidence and changed shared/root projection checks pass;
- strict parent graph completeness passes when migration, a touched manifest,
  or a selected profile requires it; otherwise the matching skipped receipt is
  retained;
- immutable PullRequestLifecycle and permission authority pass;
- expected-old merge CAS passes;
- source-main publication readback matches the authoritative merge commit/tree;
- PR Essence, reviews, and contributor diff where applicable are retained;
- one immutable source-projection packet is materialized in the explicit parent owner namespace;
- accepted QueueReceipt, pending/accepted DependencyFrontier, transaction marker, and G4 are derived there by the canonical front door;
- source/reviewer/PR descendants have durable handback, are closed, and their
  reservations are released;
- parent projection remains untouched until frontier acceptance.

## Prohibited Routes

- editing a parent/root projection as source;
- compatibility branch, wrapper, subtree, or snapshot routes;
- assumed permission or inferred remote selection;
- separate push, PR, checks, and main-push candidate/tree verdicts;
- merging a stale or unreviewed candidate;
- creating or updating PR before merge conflicts are fully resolved or before
  `origin/main` is merged into the topic candidate;
- updating a merged or closed PR head branch instead of creating a successor;
- parent pin/root sync before accepted frontier;
- manual gitlink staging or copying/fabricating QueueReceipt, DependencyFrontier, transaction marker, or G4 across namespaces;
- cleanup before remote readback or prose-only agent closeout.
