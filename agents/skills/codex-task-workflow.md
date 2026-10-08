# codex-task-workflow

<!--
@dependency-start
contract skill
responsibility Transports the selected repository task, current owner context, and completion evidence without re-owning phase procedures.
upstream design ../canonical/CODEX_WORKFLOW.md conditional phase selection
upstream design ../COMMUNICATION_PROTOCOL.md investigation and handoff packet ownership
upstream design ./agent-orchestration.md routing and owner-first read selection
upstream design ../task_catalog.yaml typed workflow and execution route selection
upstream design ../../documents/operations/BRANCH_SCOPE.md commit scope and publication evidence
upstream design ../../documents/design/request-intent-and-update-relation.md request and update projection
upstream design ../internal-routines/design-implementation-correspondence.md conditional design correspondence
upstream design ../../documents/design/semantic-responsibility-contract.md verification responsibility allocation
upstream design ../../documents/conventions/software-engineering-principles.md implementation decision owner
downstream design ../../.codex/personal/skills/codex-task-workflow/SKILL.md runtime discovery adapter
@dependency-end
-->

## Reader Map

This Skill carries the selected task between owners. Read common constraints and
only the row needed for the current action. Apply an established routing decision;
reopen selection only when new evidence changes it.

| Active operation | Read next |
| --- | --- |
| Owner, workflow, Skill, or review selection remains unresolved | [agent-orchestration](agent-orchestration.md#decision-order) |
| Current action needs owner context | [Owner-First Readback](#owner-first-readback) |
| Begin or resume execution | [Execution route](#execution-route), then the current [phase](../canonical/CODEX_WORKFLOW.md#reader-map) |
| DIC is selected by the design owner | [design correspondence](../internal-routines/design-implementation-correspondence.md); carry its selected closure before the dependent handoff |
| A selected child needs a handoff | [Coordination handoff](#coordination-handoff) |
| Validate or deliver the current result | [Codex Completion](../canonical/CODEX_COMPLETION.md#reader-map) |

A bounded owner/path/targeted-validation route uses its existing task evidence.
Only a selected coordination route creates run-bundle artifacts. DIC selection,
full staging, reviewer activation, and child activation retain their own conditions;
a link, file count, or public Skill candidate does not select them.

### Compact request/update projection

Follow the [request/update owner](../../documents/design/request-intent-and-update-relation.md).
Evidence-read closes an advisory question with an evidence-backed answer and
answer/read-scope readback. An explicit write clause carries target, operation,
owner, write set, authority, and acceptance evidence into a write-ready handoff.
An approved update changes the existing goal/artifact/order/handoff fields as a
sparse delta; preserve still-valid context and completed work.

The active DIC route alone carries DIC-010's path+section+clause/ref closure packet.
The design owner supplies it before the worker handoff and review reads changed
paths back to the selected clauses. This transport does not create another
fingerprint, semantic ledger, or traversal rule.

## Purpose

Carry the required outcome, complete responsibility unit, selected owner, actual
validation, and authorized delivery through a context-independent Codex task.
Detailed phase procedures remain in their existing canonical owners.

## Use When

Use for repository-changing execution after routing is selected. Consultation,
brainstorming, explanations, and GitHub-only read inspection keep their read/advisory
scope; they do not acquire implementation, shell, or publication work from this Skill.

## Core Reference

[Codex Workflow](../canonical/CODEX_WORKFLOW.md#reader-map) selects the current phase.
The public catalog owns Skill identities; `agents/task_catalog.yaml` owns typed
family, role, and execution-route selection. Reuse those owners rather than a second
workflow matrix here.

## Execution route

Consume `agents/task_catalog.yaml#execution_route_policy` through the
[execution-time owner](agent-orchestration.md#execution-time-aware-work-conservation-contract).
For `bounded_fast_path`, use the existing task or Issue evidence and let the
execution owner choose the needed work order from the actual dependencies and
requested operations. For `coordination`, carry the selected run-bundle evidence
to its closeout owner. Both retain the exact-diff review, selected validation,
current-base integration, authorized publication, and completion evidence that
the request requires. Unavailable required validation remains `need verification`,
not a successful check.

## Owner-First Readback

Before interpreting or changing implementation, use
[Owner-First Read Trace](agent-orchestration.md#owner-first-read-trace) to find
the selected Skill and any owner it delegates to. Read the actual constraints
that apply to the current action; follow links when they resolve a live decision
or required guarantee. `skill-document-reader` may help locate or return text,
but EOF metadata is not proof of comprehension and does not create a readiness
field or admission gate.

Use the established [checkout identity](../canonical/CODEX_INTAKE.md#optional-context)
and trace the actual in-scope dependency and consumer before selecting the replaceable
unit. Refresh only changed premises; an unperformed trace does not establish absence.
The existing-tool-before-read exception covers the tool action itself; interpreting
or repairing its output still needs the applicable owner context.

Dependency metadata records responsibility. Select decision-relevant edges using
[File Dependency Manifest](../canonical/CODEX_IMPLEMENTATION.md#file-dependency-manifest).
Carry that selected context and affected consumer closure, not a recursive inventory
of every linked document or a new per-read receipt.

## Stages

Use the current [phase row](../canonical/CODEX_WORKFLOW.md#reader-map) to locate
the owner for the action at hand, while preserving the user's `requested_scope`
and complete responsibility unit. The row is a decision aid, not a fixed
sequence: follow actual dependencies, skip inactive work, and parallelize
independent work only when authority and validation boundaries allow it. If the
request spans more than the current slice, keep covered, deferred, and omitted
surfaces with their reasons in the existing task record.

The [Design Integrity Gate](../canonical/CODEX_IMPLEMENTATION.md#design-integrity-gate)
owns the 責務 model, 差し替え可能な単位, 実装 scope, implementation mechanism,
validation route, unresolved branch, and `design_issue_blocker` decision. Resolve a
material design question with that owner before the affected implementation. The
selected coordination design packet alone materializes the run-local semantic
responsibility contract; bounded work carries the same obligations in existing
structured evidence.

Before selecting a workload-dependent mechanism, use
[workload and scale](../../documents/conventions/software-engineering-principles.md#workload-and-scale-before-mechanism).
Before adopting a tool/reviewer repair proposal, use
[reachability and remedy necessity](../../documents/conventions/software-engineering-principles.md#reachability-and-remedy-necessity).
Carry the resulting decision and design reference into implementation and review.
Investigation continues for facts that change the next action, then returns to that
action rather than another sweep.

For research-backed implementation or literature-derived design, benchmark, or report
claims, call [literature-survey](literature-survey.md) before
[research-workflow](research-workflow.md), 設計, and implementation. Carry its durable
source packet, source class, limitation, contrary evidence, and adoption/exclusion
decisions into the Implementation Source Packet or existing bounded design evidence.

Validation uses [6. Validation](../canonical/CODEX_COMPLETION.md#6-validation):
静的解析・読み取り evidence and targeted tests are primary validation evidence;
broader execution is supplemental evidence when runtime behavior, integration risk,
or a 未解決 finding requires it. Preserve required execution checks and their actual
results; read-only analysis cannot establish an unrun runtime property.

## Coordination handoff

Read this section only after the typed route selects a child or durable coordination.
Use [Coordination handoff](../canonical/CODEX_IMPLEMENTATION.md#coordination-handoff)
and the [subagent owner](../canonical/CODEX_SUBAGENTS.md) for role, model, authority,
writer placement, review separation, and lifecycle. Keep user-guided debugging in
the parent as required by the shared root.

Carry selected owner sections, request clauses, write scope, actual checkout identity,
validation route, and the protocol-owned Fresh Subagent Context Capsule. Preserve the
same warm context for same-owner revisions; distinct authority/context or independent
review selects a separate instance. Source packets are references to actual evidence,
not raw chat, full logs, dashboards, or a repo-wide reading list.

Where the selected run emits `REPO_TOOL_ROUTING_SEQUENCE`,
`REPO_TOOL_ROUTING_NEXT_COMMAND`, and `REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES`, carry
those values without activating every candidate. A newly selected related Skill gets
its own current command packet before handoff. Execute advertised logical commands
through [CLI Entrypoints](../canonical/CLI_ENTRYPOINTS.md#tool-commands).

A selected writer's failure retains its authority boundary and concrete blocker;
parent execution is not a fallback. After a nonterminal timeout, use
[Subagent Return Investigation](subagent-bootstrap.md#subagent-return-investigation)
for the next bounded observation; keep failed mutation retries distinct.

## CompletionCoverage Reader Projection

Only coordination consumes `agent-canon.completion-coverage.v1` from the existing
logical ledger. COMMUNICATION_PROTOCOL owns its schema, CODEX_COMPLETION its
applicability, and `report_artifact_checks` / `task_close` its check and consumption.
This transport reuses those owners and does not enumerate their fields, create a
second ledger, or turn a checkpoint into delivery.

## Required Output

When an execution update needs routing context, record the selected workflow,
active Skills, and review owner from the existing policy; reuse a settled
selection. Respond in the user's language and keep technical identifiers in
their actual commands, paths, tables, or evidence references. The existing task
record preserves scope, decisions, actual result, evidence, and limits through
updates and handoff.

For source maintenance use [agent-canon-update](agent-canon-update.md#change-route);
for local branch integration use [integration](integration.md); for authorized remote
publication use [pr-processing](pr-processing.md). These owners retain current-main,
conflict, commit/push, cleanup, and Issue readback obligations. Source changes do not
authorize updating a consumer's generated root or creating a live projection.

Before placing a document use [Artifact Placement](../canonical/ARTIFACT_PLACEMENT.md).
Before writing a result use [reader-facing writing](../canonical/ROOT_DELIVERY.md#reader-facing-writing).
On a failed verification go immediately to
[Failed Verification Record](../../documents/operations/notes-lifecycle.md#failed-verification-record).
Private knowledge/behavior feedback alone selects [agent-learning](agent-learning.md#reader-map).

## Runtime Contract Clauses

Apply the selected route and referenced owners. Create artifacts only under their
conditions; do not add a second phase checklist, schema, evidence ledger, or
approval gate. Route failed checks to the existing failure owner, and continue
required in-scope work through the selected Completion Readiness route.
