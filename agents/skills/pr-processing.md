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

## Execution-Time-Aware Queue Specialization

`agents/skills/agent-orchestration.md#Execution-Time-Aware Work-Conservation Contract`
owns the dependency DAG, makespan objective, ready-set dispatch, batching,
warm-context reuse, closure, and scope-preserving wait rules. This skill
specializes that contract for PR and Issue queues:

- Always-required fields: `owner`, `schema`, `dependency`, `validation`,
  `correctness`, `publication_scope`.
- Graph-only fields: `dag`, `critical_path`, `ready_set`, `queue_snapshot`,
  `makespan_objective`.
- Candidate count alone does not activate the graph. A single PR and multiple
  independent PRs remain on the bounded single-candidate route unless a
  selected edge is present.

The single-candidate fast path takes no queue-wide snapshot. The dependency
queue path activates only for a selected ordering, dependency, collision, or
publication edge and then snapshots and reviews only that selected subgraph.

1. For an active selected edge, take one immutable, batched queue snapshot for
   the selected PR and Issue subgraph, including fields required for
   classification and dependency ordering. Batch remote and tool reads while
   retaining exact candidate identity and readback evidence.
2. Compute each selected candidate's complete owner, schema, dependency,
   validation, and publication closure before its first owning review. Prepare
   and, only with the required mutation authority, publish independent
   candidates in non-conflicting lanes; do not serialize independent candidate
   preparation.
3. Run one closure review for each exact candidate after that candidate's
   closure is complete. A review finding invalidates only the affected
   candidate evidence and its dependent evidence; rerun that affected closure
   with the same warm worker and reviewer context when the route is unchanged.
4. Merge candidates in dependency order. Independent preparation and
   publication may remain batched, but a dependent source, parent pin, or root
   projection cannot merge before its accepted predecessor receipt and exact
   readback.
5. Never use elapsed time or a fixed duration to cut queue scope, skip a
   candidate, replace closure review, or declare closeout. When no useful ready
   candidate exists, record the actual dependency, conflict, capacity, or
   external-state blocker and wait for that state to change.

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

## Validation and repair

Code/doc repair remains owned by the changed surface. This skill consumes the resulting validation/review evidence and does not invent a second implementation workflow or duplicate selected gates.

## Publication boundary

Before merge/ready/close/update, read fresh remote state and confirm authority. After the write, read back the PR/issue state. These write controls apply in both single and queue modes.

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
