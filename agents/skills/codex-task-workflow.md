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

Reuse the applicable route from the [task catalog](../task_catalog.yaml), the
current target, and settled context. Begin with the requested outcome, authority,
input/output contract, and governing owner. For a failure repair, identify the
cause from the target and relevant evidence, then use the root [local repair
rule](../../ROOT_AGENTS.md#always-on-boundary). Do not restart discovery or add
phases that do not affect this task.
For execution-time clarification or a contract blocking the agreed outcome,
follow [Decision Order](agent-orchestration.md#decision-order)
to review the whole Goal, resolve retrievable facts, and ask before changing
the agreed scope, expected result, or major approach. Carry out contract-derived
repairs within existing authority. Continue independent authorized work while
a dependent change awaits the user's decision.

## Stages

Use [CODEX_WORKFLOW](../canonical/CODEX_WORKFLOW.md) to select an owner for the
next needed action. Follow actual dependencies, not a fixed stage order. Resolve
a material design question with [CODEX_IMPLEMENTATION](../canonical/CODEX_IMPLEMENTATION.md)
when it changes the implementation. Keep obsolete-support retirement with the
existing owner. A newly selected capability uses its existing CLI/API/script
with its native arguments and process-result semantics. Before adding an
implementation, compare the requested guarantee with capabilities already
identified in the caller's context. Reuse or compose one that satisfies it;
extend only to close a concrete gap. Judge overlap by responsibility and
contract, not by names or paths alone.

## Coordination handoff

Delegate or create durable coordination only when the selected route needs it.
Then follow [subagent-bootstrap](subagent-bootstrap.md),
[CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md), and
[COMMUNICATION_PROTOCOL](../COMMUNICATION_PROTOCOL.md) for the applicable role,
checkout, authority, and handoff. Parent and child retain their assigned scopes.

## Validation and delivery

Run the validation selected by the changed guarantee and its owner. Report what
the result establishes; keep failed, skipped, and unrun checks distinct. Use
[CODEX_COMPLETION](../canonical/CODEX_COMPLETION.md) for closeout when needed.
Integration or publication follows its selected owner and authorization, with
remote readback after an external write. When the task changes an operational
procedure, update the affected Skill's Use When/flow in the same work unit;
ordinary prose edits do not trigger a repository-wide Skill scan.
