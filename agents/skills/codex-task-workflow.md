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

Carry the requested repository change through its selected owners, validation,
and authorized delivery. Phase procedures remain in their canonical owners.

## Use When

Use after routing selects repository-changing execution. Advice, explanation,
and read-only inspection keep their existing scope.

## Execution route

Reuse the route from the [task catalog](../task_catalog.yaml). A bounded task
proceeds with its existing evidence and one execution owner. Coordination uses
its selected run bundle and closeout owner. Do not create a bundle or child
handoff unless the route requires one.

## Owner-First Readback

Use the applicable root instructions and selected Skill. Follow only linked
owners needed for the current decision, and preserve settled context across
phases. Trace actual callers or consumers when they can change the
implementation boundary.

## Stages

Use the current phase row in [CODEX_WORKFLOW](../canonical/CODEX_WORKFLOW.md)
to find the owner for the next action. Follow actual dependencies rather than a
fixed stage sequence; inactive phases, reviewers, and specialists remain
inactive. Resolve a material design question with
[CODEX_IMPLEMENTATION](../canonical/CODEX_IMPLEMENTATION.md) before the affected
edit. When multiple implementations or obsolete support must be retired, use
the shared [owner and retirement rule](../../ROOT_AGENTS.md#always-on-boundary).

## Coordination handoff

Use [subagent-bootstrap](subagent-bootstrap.md) only after the typed route
selects a child or durable coordination. [CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md)
owns roles and lifecycle; [COMMUNICATION_PROTOCOL](../COMMUNICATION_PROTOCOL.md)
owns handoff content. For a writing child, use
[repository-topic-clone](repository-topic-clone.md) for the prepared checkout
and target. Parent and child retain their assigned authorities.

## Validation and delivery

Use [CODEX_COMPLETION](../canonical/CODEX_COMPLETION.md) for required checks and
closeout. Report what was actually established; unavailable required
verification remains unverified. Use the selected integration or PR owner for
authorized base integration and publication, and read back remote state after a
write.


