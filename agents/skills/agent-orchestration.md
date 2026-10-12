# agent-orchestration

<!--
@dependency-start
contract skill
responsibility Selects workflow, Skill, role, and execution routes for repository work.
upstream design ../canonical/CODEX_ROUTING.md task and workflow selection
upstream design ../task_catalog.yaml typed workflow and execution route
upstream design ./catalog.yaml public Skill identity and discovery
upstream design ./skill-dependencies.yaml Skill prerequisites and ordering
upstream design ../COMMUNICATION_PROTOCOL.md collaboration capability and handoff boundary
downstream design ../canonical/CODEX_INTAKE.md owner-first read route
downstream design ../canonical/CODEX_COMPLETION.md validation and closeout
downstream design ./codex-task-workflow.md repository execution
downstream design ./pr-processing.md dependent PR queues
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
choices in a local task, use the target source, current diff, and governing
contract to decide the next action.

Use the [task catalog](../task_catalog.yaml) for workflow family, role, and
execution-route decisions. Public Skill identity and prerequisites come from the
[Skill catalog](catalog.yaml) and
[dependency map](skill-dependencies.yaml). Choose Skills by the requested
deliverable or unresolved owner decision; an available candidate is not an
activation.

When task routing activates mathematical intent, the
[computational-optimization](computational-optimization.md) Skill owns the
packet schema and numerical scope; this guide routes to that owner without
duplicating its fields.

Use bounded_fast_path when scope and contract are resolved, there is one root,
owner, and writer, and no dependency, collision, publication, or resumption need
requires coordination. Otherwise follow the catalog's coordination route. Task
size, prompt words, and risk labels do not decide the route.

Activate design, research, specialist, review, child, or durable-run routes only
when the selected owner or a distinct unresolved decision requires them. A
related document or repository change alone does not select a specialist
workflow.

## Owner-First Read Trace

Start with the applicable root instructions and selected Skill. For a local
change, use the target, current diff, and governing contract. Reuse settled
context and the selected owner route.

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

This guidance applies when coordination is selected. Use relative links from the
selected workflow to find relevant owner instructions; a link is conditional
guidance, not a requirement to read every linked document. Record actual native
tool and child results using the selected workflow's existing record. A launch
is not completion, and a route difference alone is not a failure; use existing
Eval or owner review to assess whether necessary work was missed or unnecessary
work was done.

Preserve the requested work and correctness before minimizing necessary total
work. Time limits and prompt keywords do not cut scope. Read the selected Skill's
common constraints and the content needed for the current decision, deferring
inactive branches until their conditions apply. Read applicable prerequisites
under [In-flight skill reads](task-routing.md#in-flight-skill-reads).

Review a candidate once. Repair accepted in-scope findings and recheck only
affected evidence; reopen review only when new contract, reachable-behavior, or
structural-contradiction evidence changes the candidate. Repeating the same
state and action without new evidence is a cycle, not progress.

Completion requires no unresolved request clauses or blockers, and required
validation must pass or be not applicable. PR queues use this guidance when
candidates have actual ordering or collision dependencies.

## Review Activation And Adjudication

Select one owning review gate for each responsibility. Add a specialist only for
a distinct claim or risk that the owning gate cannot judge. Treat review output as
a hypothesis; accept it only with current-source, reachable-path, contract, and
witness or static-proof evidence.

## Outputs

Return the selected route and owners, required validation, and any unresolved
fact that could change the next action. Reuse the existing task update, tool
result, or handoff.
