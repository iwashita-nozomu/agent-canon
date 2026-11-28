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
upstream design ../../references/skill-tool-coordination.md existing and external capability assessment
downstream design ../canonical/CODEX_INTAKE.md owner-first read route
downstream design ../canonical/CODEX_COMPLETION.md validation and closeout
downstream design ./codex-task-workflow.md repository execution
downstream design ./pr-processing.md dependent PR queues
@dependency-end
-->

## Purpose

Select the next owner and execution route from the request and current context.
Use at intake or when new evidence changes that choice.

## Decision Order

Use the agreed outcome, target, and governing sources to choose the owner and
route. Read the relevant assumptions before assessing an approach. Reconsider the
route when evidence is missing or contradicts the expected result.

Ask before changing agreed scope, result, required properties, or major approach.
Give the checked facts and the decision's effect. Continue independent authorized work.

Use the known Skill. Consult the [task catalog](../task_catalog.yaml),
[Skill catalog](catalog.yaml), or [dependency map](skill-dependencies.yaml) for an
unresolved route. Use the bounded route for one owner and writer. Activate
specialists for a decision or guarantee they own. Route mathematical work to
[computational-optimization](computational-optimization.md) for
[loss definitions and term changes](computational-optimization.md#loss-changes)
and [hyperparameter selection](computational-optimization.md#hyperparameter-selection),
including learning-rate choices and diagnosis of poor training settings.

## Delegation selection

Prefer the current agent under [ROOT](../../ROOT_AGENTS.md#task-entry). Delegate
for an explicit request, needed independent judgment, or useful separable work;
weigh context transfer and integration against the benefit. Keep sequential work
and compatible continuation together. Publication or resumption alone needs no
child; available slots and role inventories do not require filling them.

## Owner-First Read Trace

Start with the target and its governing source. Follow references that establish
an assumption or could change the decision, including after a contradictory result.

## Skill and tool cooperation

Use existing tools at their actual target and judge results against the request.
Follow pending operations to their result. On failure, check the input and the
owning boundary, then resume the requested operation by a supported route.
Use [reuse feasibility](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
when the choice of an existing capability matters.

## Local Capability Priority

Reuse known local/host ownership and the [task skill set](README.md#task-skill-sets).
Direct-peer communication needs observed runtime capability; otherwise use parent
relay or a durable artifact. The [communication protocol](../COMMUNICATION_PROTOCOL.md)
owns that selected handoff. Return provider results to the content owner.

## Write-Capable Handoff Validation Trust Boundary

Run assigned commands and mechanism-required static/read-only checks. Do not add
default suites or restart running checks. Return unexpected routes to the owner;
unavailable required verification stays unverified.

## Decision Sufficiency Packet

Resolve only questions that could change outcome, mechanism, or validation using
current owner evidence. Carry decisions in the conversation or native handoff.
No separate work ledger is needed for coordination or resumption.

## Review Activation And Adjudication

Choose one owning review for the responsibility. Add a specialist for a distinct
claim that owner cannot judge. Verify findings against current contracts,
reachable effects, and a witness or sound static evidence before repair.

## Outputs

When routing is requested, return the selected owner/route, required validation,
and unresolved decisions. Otherwise apply the route and report facts affecting
progress through the existing task update or handoff.
