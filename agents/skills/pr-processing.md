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

## Validation and repair

Code/doc repair remains owned by the changed surface. This skill consumes the resulting validation/review evidence and does not invent a second implementation workflow or duplicate selected gates.

## Publication boundary

Before merge/ready/close/update, read fresh remote state and confirm authority. After the write, read back the PR/issue state. These write controls apply in both single and queue modes.

## Completion

A single PR completes when its blocking findings/required validation are closed and the requested publication state is read back. A queue completes according to its dependency graph and requested scope; unrelated candidates do not become implicit obligations.
