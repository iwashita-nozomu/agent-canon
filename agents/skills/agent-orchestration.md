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

Resolve the workflow, owners, Skills, and validation route for a repository task.
The selected owner performs the work; this Skill does not replace its procedure.

## Use When

Use at repository-task intake or when new evidence could change the selected
owner, workflow, delegation, or execution route, or a contract blocks the requested
outcome during implementation or validation.

## Decision Order

Start from the active Goal's whole objective and current instruction, or the
current request when no Goal exists. Retain agreements and review authorized
scope, completed and remaining work, dependencies, blockers, and next actions.
Classify advisory/read-only or repository-changing work. Reuse applicable
instructions and owner context; read only within the
[current read authority](../../ROOT_AGENTS.md#always-on-boundary).
Local decisions use the target, current diff, and governing contract.

Before asking the user, recover applicable earlier requests and retrievable
facts from permitted code, tests, docs, history, and tool results. Continue
authorized work when these sources can resolve the gap. Ask early once evidence
identifies a material user-owned choice; do not ask for known requirements or
retrievable facts, or require exhaustive investigation first.

For a blocking contract, identify its owner, revision, path and clause/symbol,
the requested result, blocked operation, and conflict evidence. Implementation
or execution failure alone does not establish a governing contract or conflict. When
agreements, instruction precedence, and facts uniquely settle the resolution,
state that basis and perform the authorized correction. Otherwise ask whether
to retain, revise, or extend the contract. Preserve acceptance and higher-priority
safety/authority limits; do not silently preserve or bypass the blocker.

Before changing agreed scope, expected result, major approach, or an unsettled
blocking contract, ask a self-contained question: settled requirement, checked
behavior, user-owned choice, proposed change, recommendation, alternatives'
effects, and the action awaiting an answer. Include contract location/conflict
evidence when applicable. An active Goal or internal design does not authorize
the change. Wait on dependent changes while continuing independent work. Ask
also for required user-owned input/authority unavailable from permitted sources.
Retain evidence, question, answer, and rationale in the existing task, Issue, or
handoff; a blocker report alone is not that question.

Complete authorized contract-derived repairs, including required input preparation
or missing API behavior. Scope follows contract and cause. Honor write, stop, and
pause boundaries; do not re-ask settled choices or routine implementation decisions.

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

## Delegation selection

Apply the [current-agent default](../../ROOT_AGENTS.md#task-entry) before choosing
a child. Identify the separate judgment or bounded work it would own and the
concrete benefit of separating it. Weigh that benefit against context transfer,
duplicated investigation, waiting, verification, and integration. Qualitative
task evidence is sufficient; keep the work in the current agent when the
benefit is unclear.

Keep tightly coupled or sequential steps together. Select the smallest
sufficient delegation when independent work can usefully proceed in parallel or
the task requires an independent judgment. Preserve explicit collaboration
requests and required independent reviews. Use existing deterministic checks
for the properties they establish.

A need for durable coordination, resumption, or publication can be handled by
the current agent; choose additional agents separately. Role inventories and
available capacity describe candidates and limits. Reassess the benefit before
adding another child, using the existing task context.

## Owner-First Read Trace

Start with the applicable root instructions and selected Skill. For a local
change, use the target, current diff, and governing contract. Reuse settled
context and the selected owner route.

## Skill and tool cooperation

The selected Skill owns the task decision and acceptance; the tool provider owns
its native interface, execution state, and effects. Connect the property needed
for the next Skill decision to an available tool and its actual inputs and
outputs. Reuse the current contract and source binding; consult exposed schemas,
catalog entries, help, or source only for an unresolved part of that call.

Compose existing operations through their native interfaces using
[reuse feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support).
Carry the actual target, execution plane, arguments, output location, and needed
data conversion across the call. Preserve the provider's ordering, ownership,
and shared effects when deciding which operations can run concurrently.

Follow the provider's execution state for the requested operation. For unfinished
work, follow its documented completion mechanism and preserve any returned
handle. Consume the completed result when completion is reported. Retain failures
and partial results as evidence. For truncated output,
use its reported locator or pagination to obtain the part needed for the
decision. Feed actual returned values and artifacts into the next operation.

Apply the Skill's acceptance to the returned evidence and its coverage. A
successful tool exit establishes that tool's own completion guarantee. If the chain
does not meet the task contract, compare expected and actual inputs and outputs
at the failing boundary. Distinguish input preparation, missing API behavior,
runtime failure, and a mismatched Skill expectation; repair through the existing
owner within the agreed scope. Use [tool-finding-report](tool-finding-report.md)
when findings need a repair or reporting handoff, then return to the interrupted
operation and the requested result.

## Local Capability Priority

When local, deferred, or split operations compete, reuse the task/handoff record.
Direct-peer collaboration requires a reported runtime capability; otherwise use
parent relay or a durable artifact. The [communication protocol](../COMMUNICATION_PROTOCOL.md)
owns receipts and packet fields.

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

When coordination is selected, follow only applicable owner links and record
actual tool/child results in the existing workflow record. A launch is not
completion; a route difference alone is not failure. Use existing Eval or owner
review to judge missing or unnecessary work.

Preserve correctness and requested scope. Reuse current context, load missing
common constraints and selected guidance, and defer inactive branches under
[In-flight skill reads](task-routing.md#in-flight-skill-reads). Time limits and
prompt keywords do not cut scope.

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
