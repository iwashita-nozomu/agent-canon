# Codex Implementation

<!--
@dependency-start
contract agent-runtime
responsibility Owns design admission, implementation scope, dependencies, and implementation execution.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

## Reader Map

Read common implementation decisions, then the section for the active operation.
Select only the sections applicable to the current responsibility. Do not read
unselected coordination guidance by default. Return to
[Codex Workflow](CODEX_WORKFLOW.md#reader-map) when the task context changes.

| When | Read |
| --- | --- |
| A requested repair has no established causal code | [cause localization](../skills/dependency-analysis.md#method) |
| Choosing or correcting the implementation contract | [Design Integrity Gate](#design-integrity-gate) |
| Selected design work needs a durable packet | [Coordination design packet](#coordination-design-packet) |
| Editing a repository file | [Edit Execution Surface](#edit-execution-surface) |
| Selecting an implementation or adding code/API | [Library And Reuse Sweep](#library-and-reuse-sweep) |
| Explicitly analyzing or editing a dependency-graph annotation | [File Dependency Manifest](#file-dependency-manifest) |
| Executing the approved implementation | [5. Implementation](#5-implementation) |
| Diagnosis or cause repair interrupts requested code work | [Return from a repair detour](#return-from-a-repair-detour) |
| Delegating implementation under a coordination route | [Coordination handoff](#coordination-handoff) |

## 契約完全実装

Keep request clauses, valid inputs, guarantees, acceptance evidence, and the
complete affected responsibility unit through design, implementation, and review.
Use [implementation decisions](ROOT_IMPLEMENTATION.md#simplest-complete-implementation)
for the engineering basis. Markdown links and actual dependency/ownership facts
guide work; they do not narrow the requested outcome. Update the selected owner
when newly established contract facts require it.

## Design Integrity Gate

For a repair whose causal location or mechanism is unresolved, first use
[cause localization](../skills/dependency-analysis.md#method) before choosing a
fix. Reuse established evidence rather than restarting diagnosis.
For the selected change, establish the owner, mechanism, required guarantee,
affected responsibility unit, evidence, and unresolved decisions that could
change the edit before changing it.
Use [agent orchestration](../skills/agent-orchestration.md#decision-sufficiency-packet)
for decision sufficiency and reuse current owner evidence. Return an unresolved
decision to its design owner with `design_issue_blocker` evidence when it can
change the agreed outcome or method, a boundary interface, valid input domain,
state/ownership invariant, or required guarantee. Resolve local naming, placement,
and edit order during implementation when they preserve that contract, using
[necessary design conditions](ROOT_IMPLEMENTATION.md#contract-and-valid-domain).
When a contract
blocks the agreed outcome, follow [Decision Order](../skills/agent-orchestration.md#decision-order)
to expose the conflict and ask the user about a resolution not settled by the
available evidence; an internal blocker report alone does not resolve it.
A verified root correction preserves the agreed intent while changing defective
contracts and their consumers as necessary.

Markdown links identify the expected owner and Skill route; they do not create a
dispatch frontier. When delegation is selected, use the configured native
collaboration route and preserve actual launch, completion, and failure results.
Repair a selected tool's refusal at its owner, then resume the authorized
operation. Runtime identity, spawn, and writer-packet records are not editing
permission gates.

A bounded route's selected execution owner performs its edit and verification
without a child handoff. When the selected route requires full staging, read
[Coordination design packet](#coordination-design-packet) before that handoff.
When a selected design needs comparison with the diff, use
[design-to-diff review](../internal-routines/design-implementation-correspondence.md).

## Coordination design packet

Read the selected design for the requested behavior, assumptions, interfaces,
side effects, and verification. Carry the necessary references in the native
handoff. Mathematical obligations, proof and experiment artifacts keep their
domain owners. Use existing project paths; no task manifest, fingerprint file,
or custom runtime gate is required.

Activate a separate detailed-design or document-flow review only for a distinct
unresolved judgment. Preserve accepted findings and recheck the affected evidence
when the design changes.

## Edit Execution Surface

Use patch-based edits for changes whose responsibility can be traced manually.
Use the repository's existing generator, transformer, or formatter for mechanical
changes. Preserve unrelated/user-owned content and review the resulting diff.
The requested scope remains authoritative. Keep the selected change and its
source-backed scope decisions in the current conversation.

For document creation, splitting, movement, or deletion, first read
[placement and references](ARTIFACT_PLACEMENT.md#置き場ルール). Formatting follows
the common [Validation Routing](../../ROOT_AGENTS.md#validation-routing).

## Library And Reuse Sweep

For a change to existing functionality, trace the selected entrypoint through
its shared components to the requested change. Modify the owning component and
use that execution path to produce the requested result. A separate execution
path requires a demonstrated gap in the existing implementation and prior
agreement on the resulting scope or approach change.

When the connection between existing capabilities is unresolved, construct its
concrete call flow through [reuse
feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
using the target contract and known providers. Extend the investigation only for an unknown
entrypoint, failed invocation, or unmet behavior that could change the decision;
reuse [prior failed attempts](../../documents/operations/notes-lifecycle.md#retrieve-before-deciding)
when they bear on it. This does not require a repository-wide survey or new packet.

When a related branch/PR or prepared checkout exists, verify it serves the same
owner surface and continue it through [Branch Reuse Default](CODEX_INTAKE.md#branch-reuse-default)
and [repository-topic-clone](../skills/repository-topic-clone.md) before creating a new path.

## File Dependency Manifest

The [dependency manifest](../../documents/design/dependency-manifest-design.md)
is optional metadata for explicitly selected graph analysis. Ordinary file
creation, editing, and PR validation do not require a manifest or a matching
`contract` entry.

For ordinary scope discovery, follow actual import/include/call-site references,
standard links, build/package configuration, and the responsible owner routes.
Existing dependency annotations may add useful context when present. Add or
change an annotation only when the requested work changes that annotation or an
explicit graph-analysis task needs it. Missing annotations are not a repair
requirement for other file changes.

When an annotation itself is edited, preserve its declared relation semantics,
repository-relative paths, target existence, and comment syntax. For code
changes, use the existing LSP/code-dependency owner to follow definitions,
references, and callers through affected contracts. Handoffs carry the
decision-relevant source evidence and consumer closure; they do not require an
all-edge recursive listing, `dependency_edit_scope.txt`, or
`dependency_graph.tsv` on every task.

The `dependency-analysis` [Method](../skills/dependency-analysis.md#method) also
owns cause localization for a requested repair. Its optional header scanning,
format, graph, and design-claim tools are separate conditional operations, not
generic gates for ordinary edits.

## 5. Implementation

Implement from the agreed design, current canonical paths, and selected
validation route. Carry the current objective and acceptance, active
requirements, relevant retirement reasons, and unresolved points in the existing
task or handoff; the latest explicit user instruction governs conflicts while
compatible earlier requirements remain active. Before editing or restoring
behavior, define the intended outcome across changed and retained requirements;
use history for rationale, not correctness.

For the planned repair or migration, follow this order:

1. Decide what changes and how before editing: the required behavior, retained
   implementation, affected callers, and obsolete paths/symbols to delete.
   Group the work into complete units by responsibility and dependency.
2. Implement each unit in dependency order: connect callers to the retained
   API, then delete superseded code and its exclusive helpers, configuration,
   build targets, dependencies, and fixtures under
   [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement).
   Move tests for retained guarantees to that API and preserve shared support.
3. Inspect the actual diff and search old paths, symbols, imports, dispatch,
   and build references within the affected responsibility. Use existing
   reference tools when text search cannot establish reachability. Remove
   missed code and migrate remaining callers before validation; explain retained
   old code by a current requirement in the existing task/PR context.
   Complete the [post-implementation necessity review](../skills/change-review.md#procedure)
   and delete unsupported stabilization and unnecessary added variables in this unit.
4. Format the final state and run its selected tests and checks together.

The final-state review catches code left behind when a new path works; tests of
the new path alone do not establish deletion. If the change makes no code
obsolete, retain the required implementation without forcing unrelated deletion.

Use existing failure evidence to settle the repair decision before the next
implementation pass. Intermediate helpers, edits, and commits do not require
separate test runs. Planning and handoff use the current context, without work
ledgers, scope tables, or replacement-tracking files.

For a failed test or unavailable execution, use the
[test responsibility contract](../../documents/conventions/coding-conventions-testing.md#3-unit-test-contract)
to distinguish missing input preparation from missing required API behavior,
then repair the owning responsibility within the agreed contract and authority.
When that repair interrupts other code work, retain and use its
[return point](#return-from-a-repair-detour).
Before changing that scope, expected result, or major approach, follow
[Decision Order](../skills/agent-orchestration.md#decision-order) and obtain
the user's decision; an internal design correction does not supply it.
Keep design-to-code correspondence at responsibility and symbol granularity.
Correct complete mechanisms and affected consumers, retire superseded support,
avoid parallel copies, stale wrappers, configuration mirrors, and backup truth
surfaces, and preserve the complete valid domain and necessary safety, failure,
performance, and compatibility guarantees.

Before new naming or renaming, use [naming](../../documents/rule/naming.md) and
language conventions to settle concepts, vocabulary, existing naming family,
and adopted names in the existing design/task context. Only an activated
coordination route materializes its naming/design packet. New source facts that
change the mechanism or owner return to that design decision with evidence;
straightforward corrections derived from the approved contract stay in the same
implementation pass.

Read related Skills when their condition becomes true: general explanatory
structure uses [long-form-writing](../skills/long-form-writing.md), scholarly text
uses [academic-writing](../skills/academic-writing.md), and submission/thesis drafts
use [paper-writing](../skills/paper-writing.md). Additional document-flow,
completeness, notation, logic, or citation reviewers require a distinct unresolved
claim beyond the current owning gate. Candidate review packs do not activate them.

For JAX export/native-runtime changes, identify the selected generic, specialized,
or export-based path. A requested usable generic path retains its `jax.export`
producer and consumer/runtime evidence. Cross-process workers use serializable
manifests and reconstruction recipes; materialized programs retain explicit
lifetime ownership. These requirements apply to that changed contract, not to
unrelated implementations.

Continue the planned implementation and retirement review before final
validation. Carry unfinished work and established findings in the conversation.
Validation autofix follows an in-scope contract finding; unrelated style debt
stays separate.

### Return from a repair detour

Use this section when diagnosis or cause repair interrupts requested code work.
The cause owner is a repair destination, not a replacement for the task.

1. Before moving to that owner, retain the original target's repository/path and
   symbol or block, interrupted operation, and acceptance in the current context.
   Reuse the known source revision and execution route. Keep this return
   point distinct from the cause location; a changed cause hypothesis does not
   change the requested outcome.
2. Locate and repair the demonstrated in-scope cause. Once that repair and its
   selected checks permit resumption, return to the retained target, inspect the
   affected code or inputs, and perform its next unfinished operation. For nested
   repairs, resume the most recently interrupted operation first. Reuse unchanged
   evidence rather than restarting intake or unrelated diagnosis.
3. Complete the target's remaining implementation and selected acceptance check
   before taking an unrelated finding or reporting completion. When no further
   target edit is needed, explain why and continue its selected verification;
   reopening a file, promising to resume, or a cause-side pass is not that result.

A prerequisite repair's success does not prove its caller's requested behavior;
returning preserves the original acceptance as the completion criterion. A
blocked repair keeps that target and the affected property unresolved, with the
failed operation and next owner/action; continue independent authorized work.
Diagnosis-only requests and explicit stop or validation-hold boundaries retain
their agreed scope; this return step adds no edit or execution authority.

## Coordination handoff

For selected delegation, read [Codex Subagents](CODEX_SUBAGENTS.md) and the selected
role's current TOML. They own model/profile, authority, context capsule, and write
scope; this file does not duplicate the role inventory. The selected delegation
verdict supplies one implementer role/profile. Consume that verdict unchanged: a
fixed `execute_spark` packet dispatches directly to `spark_worker`; unresolved
design or repair stays with its selected reasoning owner. Do not apply a second
default, re-selection, or model fallback after the verdict is fixed.

Handoff includes the selected design path/section and request clauses, established
reuse assets and relevant tests, dependency-expanded write scope, validation route,
and current source identity. Include a test-plan artifact only when the active
workflow or unresolved runtime risk selected its creation. Consume the same
`run.subagent_prompt_packet` and role prompt contract with the fresh context capsule.
Activated design review and gate evidence must match the current artifact.
Preserve disjoint checkout/file ownership, integration order, and the selected review owner.
After each assigned unit, continue from its actual result rather than restarting
intake or expanding unselected work.
