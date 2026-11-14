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

Reuse the known route, target, agreement, and owner. Consult a catalog only for
an unresolved choice. Read a linked section only when it answers a missing
question; ordinary execution needs neither the whole phase map nor every manual.
[Decision Order](agent-orchestration.md#decision-order) owns unresolved scope or
contract choices. Resolve retrievable facts and continue independent work.

## Stages

Start from the target code, diff, and current contract. Before editing, trace
the existing caller path and shared components, then locate the owning change
and requested execution through the
[existing implementation route](../canonical/CODEX_IMPLEMENTATION.md#library-and-reuse-sweep).
Decide the complete repair unit, connecting existing APIs/CLIs and extending
the existing owner for a demonstrated gap. Use
[design admission](../canonical/CODEX_IMPLEMENTATION.md#design-integrity-gate)
for an unsettled mechanism, and [tool cooperation](agent-orchestration.md#skill-and-tool-cooperation)
for an unresolved tool/result boundary.

## Implementation and deletion

Implement complete units in dependency order: move callers to the retained API,
delete superseded code and exclusive support, inspect the final diff and old
references, then format and run the selected validation together. Preserve tests
of retained guarantees and shared support. Removal belongs to this work unit.
Complete the [post-implementation necessity review](change-review.md#procedure)
and delete unsupported stabilization and unnecessary added variables before validation.
Use the [implementation sequence](../canonical/CODEX_IMPLEMENTATION.md#5-implementation)
or [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
only for an unresolved deletion boundary; passing replacement tests alone does
not establish deletion.

## Coordination handoff

When delegation is selected, use [subagent-bootstrap](subagent-bootstrap.md) for
that handoff, scope, and continuation. A task that the current agent owns needs
no coordination document or bundle.

## Validation and delivery

Validate the changed guarantee; distinguish pass, failure, skip, and unrun work.
Correct the owning failure and resume the requested operation. Reuse unchanged
results. [Completion readiness](../canonical/CODEX_COMPLETION.md#completion-readiness)
resolves an unfinished outcome; integration/publication follows the authorized
owner and remote readback. Update the affected Skill when an operational
procedure changes. Ordinary prose edits need no repository-wide Skill scan.
