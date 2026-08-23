# pr-processing
<!--
@dependency-start
contract skill
responsibility Processes PRs with a single-candidate fast path and dependency-aware queue planning only when candidates interact.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/responsibility-rationale.md PR queue activation rationale
upstream design agent-orchestration.md execution-time-aware work-conservation contract
upstream design ../workflows/pr-queue-cleanup-workflow.md dependency-queue workflow
upstream design ../workflows/agent-canon-pr-workflow.md AgentCanon source PR workflow
upstream design ../../documents/agent-canon/agent-canon-update-route.md source PR versus parent pin route
upstream design ../internal-routines/github-status-lifecycle.md deterministic GitHub Issue status-label reconciliation and evidence contract
upstream implementation ../../tools/agent_tools/github_publish.py publishes PRs and writes summary artifacts
downstream implementation ../../.agents/skills/pr-processing/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

Process PRs/issues with fresh base/head/diff/check/authority state and explicit publication readback. Queue-wide snapshots and dependency DAGs are an optimization/safety mechanism for interacting candidates, not a prerequisite for every PR.

## Single-candidate fast path

When one PR is independent, read only what determines that PR:

1. current base/head and mergeability/conflict state;
2. actual diff and owning contract;
3. required/selected validation and review state;
4. write/merge authority and requested operation;
5. publication result/readback when a write occurs.

Do not inventory unrelated open PRs, build a full queue snapshot, or require queue-complete closure merely because the operation is PR processing.

## Dependency queue path

Build an immutable candidate snapshot and DAG only when there is evidence of source→pin order, shared changed files/conflicts, base-chain dependencies, publication order, or another cross-candidate constraint. Order execution topologically and refresh any candidate whose base/head became stale after an earlier operation.

Candidate count alone is not sufficient; activation is based on dependency evidence.

## Execution-Time-Aware Queue Specialization

This skill consumes
`agents/skills/agent-orchestration.md#Execution-Time-Aware Work-Conservation Contract`.
Its executable fields are `dependency_dag`, `responsibility_completeness`,
`correctness`, `decision_relevant_total_work`, `makespan_objective`,
`critical_path`, `ready_set`, `context_reuse`,
`affected_evidence_invalidation`, `candidate_epoch`,
`blocking_finding_ids`, `focused_recheck`, and `terminal_state`.

Use a batched queue snapshot only for interacting independent candidates.
Each candidate epoch gets one initial owning review with stable blocking finding
IDs. Repairs reuse the same warm worker and reviewer context, invalidate only
the affected candidate evidence, and receive a focused recheck rather than a
new broad review. Merge candidates in dependency order. Advisory or duplicate
findings do not create another implementation or review wave.

## Validation and repair

Code/doc repair remains owned by the changed surface. This skill consumes the resulting validation/review evidence and does not invent a second implementation workflow or duplicate selected gates.

## Base integration and merge readiness

This sequence activates only when the requested operation can merge a PR or
declare its head handoff-ready:

```text
snapshot -> refresh_base -> integrate_on_pr_branch -> resolve
         -> validate_integrated_head -> push_and_readback
         -> merge(expected_head) -> post_merge_readback
```

1. Snapshot repository-qualified base/head refs, remote base HEAD, PR head
   commit/tree, merge base, behind/conflict state, local dirty state when used,
   reviews, unresolved threads, and required/selected checks.
2. Refresh the selected remote base immediately before integration.
3. Merge that base into the PR branch, or use the repository owner's explicit
   rebase policy. Never commit conflict resolution directly to the base branch;
   preserve unrelated user-owned state.
4. Resolve each conflict against current production/design/test/document and
   generated-surface owners. Remove markers and temporary workflows, and update
   stale PR claims about SHA, paths, ownership, or validation.
5. Validate the exact integrated head. Pre-integration checks are stale.
6. Push the same branch without force and read back remote head/tree,
   mergeability, checks, reviews, and threads. Remote head must equal the
   validated head.
7. Merge only with that remote head as the expected SHA.
8. Read back merge method/commit/tree, post-merge base HEAD, merged paths,
   temporary-workflow absence, relevant gitlink state, and Issue close
   conditions.

```text
automatic_merge_ready :=
  integrated_base == current_remote_base
  and conflict_paths == empty
  and selected_validation in {pass, not_applicable}
  and required_checks == pass
  and blocking_reviews == empty
  and unresolved_threads == empty
  and remote_head == validated_head
  and pr_description_is_current
```

Stop when any term is unproven. Do not reuse old checks, infer conflict-owner
intent, ignore branch-owned failure, or merge after head/base movement. The
AgentCanon source-lane workflow is the concrete regression fixture for this
ordering; this skill consumes it without duplicating its machine schemas.

## Executor-unavailable validation evidence

Classify external CI as `executor_unavailable` only for the exact PR head when:

```text
executed_step_count == 0
and runner_assigned == false
and executor_side_annotation is present
and branch_code_executed == false
```

Billing/spending-limit, runner-allocation, or service-outage evidence can satisfy
the annotation term. If any repository-owned step started and failed, the result
is `branch_owned_failure`; local success cannot replace or downgrade it.

For an admitted unavailable executor:

1. Fix repository, PR URL, base SHA, and head SHA; use a clean checkout and
   read back dirty state.
2. Run the unchanged validation command/profile selected by the parent
   repository in its canonical container/toolchain. Record GPU-visible and
   GPU-hidden lanes separately when they prove different properties.
3. Record repository/base/head, checkout state, image/config identity,
   toolchain versions, exact command/exit, test registered/passed counts,
   GPU visibility/provider when applicable, executor/timestamp, and external
   run/job/annotation locators.
4. Publish it as `local_validation_evidence`, not as a replacement green GitHub
   status.
5. Require independent review and explicit human merge authority under the
   repository policy. This path never makes `automatic_merge_ready` true.

A later hosted retry on the same head is the authoritative hosted result. A
changed head invalidates both the classification and local evidence. PR
readback distinguishes:

```text
branch_owned_failure
validation_passed
validation_not_run
executor_unavailable
runtime_verification_required
```

## Merge and validation evidence

```text
base_ref=<owner/repository:branch>
base_head_before=<sha>
base_head_integrated=<sha>
pr_head_before=<sha>
pr_head_after_resolution=<sha>
merge_base=<sha>
conflict_paths=<ordered paths or none>
validation=<exact commands and results>
external_ci_state=<pass|branch_owned_failure|executor_unavailable|not_applicable>
local_validation_evidence=<locator or none>
review_state=<approvals/blocking/unresolved>
required_checks=<pass|fail|executor_unavailable with reason>
merge_expected_head=<sha>
merge_commit=<sha or none>
post_merge_base_head=<sha or none>
```

## Publication boundary

Before merge/ready/close/update, read fresh remote state and confirm authority. After the write, read back the PR/issue state. These write controls apply in both single and queue modes.

## Repository-qualified Issue identity

Before reading, writing, linking, deferring, or reporting an Issue, resolve the
Issue repository and number from fresh remote state. The canonical textual
identity is `owner/repository#number`.

- Use the repository-qualified identity in agent-produced progress updates,
  handoff packets, Issue/PR comments and bodies, status reports, closeout, and
  durable evidence. Do not emit a bare `#number` as the Issue identity.
- Record `issue_repository`, `issue_number`, and `issue_ref`; when a remote
  Issue exists, also record its `issue_url`. A URL may accompany the qualified
  identity but does not replace these typed fields.
- In cross-repository work, keep `consumer_issue_ref` and
  `upstream_issue_ref` separate. Do not infer either repository from the
  current checkout, a nearby PR number, or the last Issue mentioned in chat.
- Confirm that the Issue number exists in the named repository before a write.
  Use the same qualified identity in the post-write readback.

## GitHub Issue status lifecycle delegation

When an explicit request or repository policy requires status label mutation on a linked Issue, invoke the private `_github-status-lifecycle` runtime skill inside this publication boundary.

`pr-processing` owns target Issue/PR resolution, the initial fresh remote snapshot,
write authority, transport invocation, and final publication readback. Load the
repository's `documents/operations/issue-label-taxonomy.toml` mapping and pass it,
the lifecycle facts, trace evidence, and PR identity to the private routine. The
routine owns lifecycle classification, evidence admission/retry identity, ordered
single-label operations, observable concurrency stops, and the final predicate.

The caller consumes the typed adapter result and does not duplicate its transition
table, evidence protocol, or success predicate. It does not use full-label
replacement, create labels, edit/delete historical evidence, close Issues, approve
PRs, or merge as a status side effect. Concurrent drift, partial API failure, or
readback mismatch leaves publication incomplete and is reported with the exact
typed state returned by the routine.

Status reconciliation is conditional. Read-only inspection, ordinary review, and PR processing without an explicit Issue status requirement do not activate it.

## Completion

A single PR completes when its blocking findings/required validation are closed and the requested publication state is read back. A queue completes according to its dependency graph and requested scope; unrelated candidates do not become implicit obligations.
