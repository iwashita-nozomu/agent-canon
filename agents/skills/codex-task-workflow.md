# codex-task-workflow

<!--
@dependency-start
contract skill
responsibility Carries a selected repository-changing task through its current owners and closeout.
upstream design ../canonical/CODEX_WORKFLOW.md phase selection
upstream design ../canonical/CODEX_IMPLEMENTATION.md design and implementation ownership
upstream design ../canonical/CODEX_COMPLETION.md validation and delivery
upstream design ../COMMUNICATION_PROTOCOL.md handoff boundary
upstream design ../task_catalog.yaml workflow and execution route
downstream design ../../.codex/personal/skills/codex-task-workflow/SKILL.md runtime discovery adapter
@dependency-end
-->


## Purpose

Carry a selected repository change through implementation, verification, and
authorized delivery.

## Use When

Use after routing selects a repository change. Read-only advice keeps its scope.

## Execution route

Work from the target, agreed outcome, and governing contract. Reuse the existing
owner and tools. Use [Decision Order](agent-orchestration.md#decision-order) for
a missing decision and [cause localization](dependency-analysis.md#method) when
the failure owner is unclear.

## Implementation and deletion

Keep caller changes and retirement in the same change. Review the final diff
and references for obsolete code, unsupported stabilization, and unnecessary
variables using [change-review](change-review.md#procedure).

## Coordination handoff

When selected, use [subagent-bootstrap](subagent-bootstrap.md) for the handoff.

## Validation and delivery

Use the final artifacts and results to assess
[completion readiness](../canonical/CODEX_COMPLETION.md#completion-readiness).
When a required property fails or remains unverified, reconsider the assumptions
and method. Complete the remaining authorized work.

When the requested work is complete, report the result and wait for the user's
next instruction. Plan or begin a subsequent task only after the user requests it.
