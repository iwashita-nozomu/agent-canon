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
Select any child section separately; later-stage and inactive coordination
procedures remain unread. Return to [Codex Workflow](CODEX_WORKFLOW.md#reader-map)
when the phase changes.

| When | Read |
| --- | --- |
| Choosing or correcting the implementation contract | [Design Integrity Gate](#design-integrity-gate) |
| Selected typed route requires full staging | [Coordination design packet](#coordination-design-packet) |
| Editing a repository file | [Edit Execution Surface](#edit-execution-surface) |
| Selecting an implementation or adding code/API | [Library And Reuse Sweep](#library-and-reuse-sweep) |
| Editing a checkable canonical file or its dependency relation | [File Dependency Manifest](#file-dependency-manifest) |
| Executing the approved implementation | [5. Implementation](#5-implementation) |
| Delegating implementation under a coordination route | [Coordination handoff](#coordination-handoff) |

## 契約完全実装

Keep request clauses, valid inputs, guarantees, acceptance evidence, and the
complete affected responsibility unit through design, implementation, and review.
Use [implementation decisions](ROOT_IMPLEMENTATION.md#simplest-complete-implementation)
for the engineering basis. Routing, waves, bounded work packets, and validation
profiles order work; they do not narrow the requested outcome. Update a route
when newly established owner/contract facts require it.

## Design Integrity Gate

Once cause and required guarantee show that an edit is necessary, establish the
owner, mechanism, affected responsibility unit, evidence, and unresolved decisions
that could change the edit before changing it.
Use [agent orchestration](../skills/agent-orchestration.md#decision-sufficiency-packet)
for decision sufficiency and reuse current owner evidence. An unresolved API,
algorithm, dependency, configuration, naming, oracle, or responsibility decision
returns to its design owner with `design_issue_blocker` evidence. A verified root correction preserves the agreed
intent while changing defective contracts and their consumers as necessary.

The selected `workflow_activation_policy` owns child activation and authority.
A blocked selected child preserves that boundary; it does not create a parent
write fallback. User-guided debugging uses the common ROOT exception.

A bounded route's selected execution owner performs its edit and verification
without a child handoff. When the selected route requires full staging, read
[Coordination design packet](#coordination-design-packet) before that handoff.
Only an activated design-correspondence route reads
[DIC](../internal-routines/design-implementation-correspondence.md) and carries
its clause/fingerprint/closure evidence. Neither a document link nor the presence
of a design file activates DIC, full staging, or a separate reviewer.

## Coordination design packet

This section applies only to the selected full-staging route. Its
`team_manifest.yaml#run.active_design_packet` is the persisted artifact authority,
with schema `waterfall.design_packet.v1`. Preserve the selected design artifact,
technical review, document-flow review paths, and `document_flow_required` flag.
Selection precedence is explicit `--active-design-packet`, workflow-specific
record, then the standard `agents_config` artifact registry. Consumers read the
persisted selection rather than deriving new paths.

Before the implementation handoff, read the selected Abstract Design Frame,
Implementation Source Packet, Design Side-Effect Map, and Design-To-Implementation
Trace. The packet references the populated run-local
`artifact:semantic_responsibility_contract.toml`, which allocates semantic deltas,
implementation actions, obligations, primary verification owners, supporting
properties/roles, and hard-edge closure. Keep one instance shared with review.
Missing/unknown/invalid fields, schemas, or outside-bundle paths return a typed
blocker to the packet owner.

Activate a separate detailed-design or document-flow review only for a
distinct unresolved claim/risk the current owning gate cannot decide. Activated reviews must reference the same
manifest-declared design and provide their normalized decisions; required
`document_flow_required` approval remains necessary. Gate transitions use the
existing waterfall gate owner and current review evidence. Changed design
invalidates the affected review, not every unrelated gate.

## Edit Execution Surface

Use patch-based edits for changes whose responsibility can be traced manually.
Use the repository's existing generator, transformer, or formatter for mechanical
changes. Preserve unrelated/user-owned content and review the resulting diff.
The requested scope remains authoritative; retain the selected change unit and
source-backed scope decisions in the existing task/handoff rather than creating
a second scope ledger.

For document creation, splitting, movement, or deletion, first read
[placement and references](ARTIFACT_PLACEMENT.md#置き場ルール). Formatting follows
the common [Validation Routing](../../ROOT_AGENTS.md#validation-routing).

## Library And Reuse Sweep

Before any new code path, helper, API, module, test, or script, inspect the owning
abstractions and the existing dependency/build declarations, public configuration,
extension points, source, and actual callers. Use
[reuse feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
and [prior failed attempts](../../documents/operations/notes-lifecycle.md#retrieve-before-deciding).
Choose direct use/configuration/composition for new functionality; reconsider
preservation and compare removal/replacement for repairs. Record the verified
remaining gap and engineering basis in the owning design.

An existing `reuse_survey` supplies current asset and test context; reuse it under
matching premises. Tests are evidence of current behavior, not a veto on the
agreed correction. Preserve the necessary shared asset/history findings through
related handoffs and consolidate changes to the same responsibility.

## File Dependency Manifest

For checkable canonical design, workflow, tool, policy, and template text, use
the existing [dependency manifest](../../documents/design/dependency-manifest-design.md).
Its file-relative edges record responsibility relationships, not mandatory reads.
Routine notes, generated reports, archives, commentless formats, binary, and
vendored files follow the existing scanner classification.

Read the edited file's header to select relevant owners. Follow an upstream
edge before editing only when it determines an unresolved requirement, mechanism,
or validation obligation. Trace downstream contracts and consumers affected by
the change; stop at unchanged boundaries with the required guarantee preserved.
For code changes, use the existing LSP/code-dependency owner to follow definitions,
references, and callers recursively through those affected contracts. Record an
unavailable analysis route honestly and preserve its verification gap.

Keep `upstream`/`downstream` and `design`/`implementation`/`environment` semantics,
file-relative paths, responsibility and contract metadata, and the existing
comment-format placement. Add a required missing header with the edit. For a new
relationship, update its reverse edge or record the actual migration reason in
the existing review evidence. Handoffs carry only decision-relevant dependency
and downstream evidence; they do not require an all-edge recursive reading list,
`dependency_edit_scope.txt`, or `dependency_graph.tsv` on every task.

Select the existing changed-file header/format checks for changed checkable
files. When dependency relations change, use the existing source-derived graph
check for the affected contracts. Commands are logical routes through the
[CLI owner](CLI_ENTRYPOINTS.md#tool-commands):

```text
check-dependency-headers --changed
scan-dependency-headers --changed --fail-missing
check-dependency-header-format --changed --require-header
```

The graph owner verifies normalized direction/kind, reverse relations, and cycles.
Repository-wide evidence is selected by the changed contract and validation owner,
not by a document link or a shared-canon label. Preserve required graph integrity
without expanding unrelated baseline findings into this task's completion work.

## 5. Implementation

Use the agreed design, current canonical paths, existing semantic decisions, and
selected validation route. Keep design-to-code correspondence at responsibility
and symbol granularity. Correct complete mechanisms and affected consumers, retire
superseded support, and avoid parallel copies, stale wrappers, configuration
mirrors, and backup truth surfaces. Preserve the complete valid domain and
necessary safety, failure, performance, and compatibility guarantees.

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

After an implementation slice, continue remaining required work and selected
review/validation. Keep a run-local work log only for selected coordination or
resumption; otherwise use the existing task/Issue or structured handoff. Record
stale legacy scope/log observations with their owner rather than making them new
authority. Validation autofix follows an in-scope contract finding; unrelated
style debt stays separate. A failed check immediately routes to its
[topic record](../../documents/operations/notes-lifecycle.md#failed-verification-record).

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
Preserve disjoint writer targets, integration order, and the selected review owner.
After each slice, resume the remaining work under the existing route rather than
restarting intake or expanding inactive stages.
