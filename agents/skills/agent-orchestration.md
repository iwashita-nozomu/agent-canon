# agent-orchestration

<!--
@dependency-start
contract skill
responsibility Selects workflow, Skill, role, and execution routes for repository work.
upstream design ../canonical/CODEX_ROUTING.md task and workflow selection
upstream design ../task_catalog.yaml typed workflow and execution route
upstream design ./catalog.yaml public Skill identity and discovery
upstream design ./skill-dependencies.yaml Skill prerequisites and ordering
upstream design ./agent-orchestration.execution-contract.toml coordination scheduling and convergence
upstream design ../COMMUNICATION_PROTOCOL.md collaboration capability and handoff boundary
downstream design ../canonical/CODEX_INTAKE.md owner-first read route
downstream design ../canonical/CODEX_COMPLETION.md validation and closeout
downstream design ./codex-task-workflow.md repository execution
downstream design ./pr-processing.md dependent PR queues
downstream implementation ../../tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py typed contract validation
@dependency-end
-->

## Purpose

Resolve the workflow, owners, Skills, and validation route for a repository task.
The selected owner performs the work; this Skill does not replace its procedure.

## Use When

Use at repository-task intake or when new evidence could change the selected
owner, workflow, delegation, or execution route.

## Decision Order

Classify the requested operation as advisory/read-only or repository-changing.
Read the applicable repository instructions and selected owner. For unresolved
choices, inspect current source, callers, state, and constraints only far enough
to settle ownership, required behavior, scope, and validation.

Use the [task catalog](../task_catalog.yaml) for workflow family, role, and
execution-route decisions. Public Skill identity and prerequisites come from the
[Skill catalog](catalog.yaml) and
[dependency map](skill-dependencies.yaml). Choose Skills by the requested
deliverable or unresolved owner decision; an available candidate is not an
activation.

Use bounded_fast_path when scope and contract are resolved, there is one root,
owner, and writer, and no dependency, collision, publication, or resumption need
requires coordination. Otherwise follow the catalog's coordination route. Task
size, prompt words, and risk labels do not decide the route.

Activate design, research, specialist, review, child, or durable-run routes only
when the selected owner or a distinct unresolved decision requires them. A
related document or repository change alone does not select a specialist
workflow.

## Owner-First Read Trace

Start with the applicable root instructions and selected Skill. Follow a linked
owner or caller only when it can change the current ownership, implementation,
scope, or validation decision. Reuse settled context; search only when the owner
or mechanism remains unresolved.

## Local Capability Priority

Use this decision only when competing local, deferred, or split operations need
ordering. Reuse the existing task or handoff record. Select direct-peer
collaboration only after the runtime reports that capability; otherwise use
parent relay or a durable artifact. The
[communication protocol](../COMMUNICATION_PROTOCOL.md) owns receipts and packet
fields.

## Write-Capable Handoff Validation Trust Boundary

Run the commands selected in the handoff, plus only mechanism-required static or
read-only confirmation. Do not add repository-default suites or restart an
already-running check. Return a missing or unexpected route to its owner.
Unavailable required validation remains unverified.

## Decision Sufficiency Packet

Before execution, settle the owner, replaceable responsibility, mechanism,
validation route, and any unresolved branch that could change them. Reuse the
existing task or handoff evidence; create a durable packet only for coordination
or resumption.

## Execution-Time-Aware Work-Conservation Contract

This contract applies when coordination is selected. Its machine-readable details
and validation live in the
[execution contract](agent-orchestration.execution-contract.toml) and its
[checker](../../tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py).

Preserve the requested work and correctness before minimizing necessary total
work, then makespan. Model only real dependency or collision edges, dispatch
ready non-conflicting work, and wait only when no useful work is ready. Time
limits and prompt keywords do not cut scope.

Review a candidate once. Repair accepted in-scope findings and recheck only
affected evidence; reopen review only when new contract, reachable-behavior, or
structural-contradiction evidence changes the candidate. Repeating the same
state and action without new evidence is a cycle, not progress.

Completion requires no unresolved request clauses, blockers, or required
validations, and selected validation must pass or be not applicable. PR queues use
this contract only when candidates have actual ordering or collision
dependencies.

## Review Activation And Adjudication

Select one owning review gate for each responsibility. Add a specialist only for
a distinct claim or risk that the owning gate cannot judge. Treat review output as
a hypothesis; accept it only with current-source, reachable-path, contract, and
witness or static-proof evidence.

## Outputs

Return the selected route and owners, required validation, and any unresolved
fact that could change the next action. Reuse the existing task update, tool
result, or handoff.
