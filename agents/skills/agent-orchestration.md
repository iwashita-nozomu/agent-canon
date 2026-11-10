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

1. Reuse the active Goal, latest agreement, source identity, and settled decisions.
   Identify the requested operation: advice/read-only work, editing, testing,
   integration, publication, or runtime administration. Planning an operation
   does not select its execution procedure.
2. Start at the target, current diff, and governing contract. Trace affected
   callers, tests/checkers, and distribution inputs with targeted searches;
   include their necessary changes in the same responsibility unit. Resolve retrievable
   facts before asking the user. For an unresolved contract conflict, identify
   its owner/section, requested result, blocked action, and evidence. Apply a
   resolution settled by current authority and requirements; otherwise ask the
   user about the remaining choice.
3. Ask before changing agreed scope, expected result, required properties, or
   major approach. Give checked facts, the choice and its effect, recommendation,
   and dependent action. Wait only on dependent work. Complete repairs derived
   from the agreed contract without re-asking routine decisions.
4. Use the known Skill directly. Consult the [task catalog](../task_catalog.yaml),
   [Skill catalog](catalog.yaml), or [dependency map](skill-dependencies.yaml)
   only for an unresolved route, identity, or prerequisite. Built-ins use their
   registered entry; [task skill sets](README.md#task-skill-sets) resolve an
   unknown composition. Related Skills are candidates, not mandatory reads.
5. Use `bounded_fast_path` for one resolved root, owner, and writer unless actual
   dependencies, collisions, or selected coordination require another route.
   Activate design/research/review only for the decision or guarantee it owns.
   Mathematical intent routes to [computational-optimization](computational-optimization.md).

## Delegation selection

Prefer the current agent under [ROOT](../../ROOT_AGENTS.md#task-entry). Delegate
for an explicit request, needed independent judgment, or useful separable work;
weigh context transfer and integration against the benefit. Keep sequential work
and compatible continuation together. Publication or resumption alone needs no
child; available slots and role inventories do not require filling them.

## Owner-First Read Trace

Use loaded instructions and the selected target first. Read independent target,
caller, test-oracle and distribution references together, then decide the repair,
deletions and validation from those results. Further lookup needs a missing fact
that could change that decision. For a read-only plan, return that plan once these
are settled. Branch, publication, runtime and coordination manuals apply when
those operations are selected; links identify owners rather than a reading list.

## Skill and tool cooperation

The Skill owns acceptance; the provider owns its interface, execution state, and
effects. Compose known APIs/CLIs with their actual target, execution plane,
arguments, and output. Use [reuse feasibility](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
only for a concrete reuse decision. Read schema/help only for an unresolved call.
Batch independent calls, preserving ordering and shared effects. Keep a single
operation's invocation direct; correct a call syntax error before retrying.

Keep a returned handle and follow the provider's completion mechanism. Use actual
outputs in the next call; obtain only the needed missing slice of truncated
results. Apply acceptance to completed evidence. For a failure, compare expected
and consumed inputs/outputs, distinguish setup, API, runtime, and Skill defects,
repair the owner, then resume the original operation. Use
[tool-finding-report](tool-finding-report.md) when a findings handoff is needed.

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

## Execution-Time-Aware Work-Conservation Contract

For selected coordination, reuse actual tool/child results and context; follow
only applicable [in-flight reads](task-routing.md#in-flight-skill-reads). Launch
is not completion. Repair accepted findings and recheck affected evidence;
repeat review only for new decision-relevant evidence. Time limits and keywords
do not narrow the requested outcome. Apply the existing
[completion owner](../canonical/CODEX_COMPLETION.md#completion-readiness) to
unfinished requirements; PR queue planning applies only to dependent candidates.

## Review Activation And Adjudication

Choose one owning review for the responsibility. Add a specialist for a distinct
claim that owner cannot judge. Verify findings against current contracts,
reachable effects, and a witness or sound static evidence before repair.

## Outputs

When routing is requested, return the selected owner/route, required validation,
and unresolved decisions. Otherwise apply the route and report facts affecting
progress through the existing task update or handoff.
