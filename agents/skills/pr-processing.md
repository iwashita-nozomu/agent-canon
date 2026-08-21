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
