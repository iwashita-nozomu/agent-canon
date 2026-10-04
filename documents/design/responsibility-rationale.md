# AgentCanon responsibility rationale
<!--
@dependency-start
contract design
responsibility Canonical rationale and activation boundaries for reusable AgentCanon skills, gates, workflows, diagnostics, and durable issue publication.
upstream design README.md design canon index
upstream design ../../PHILOSOPHY.md shared design principles
downstream design ../../agents/skills/README.md skill authoring and review entry
downstream design ../../agents/skills/skill-cleanup.md skill procedure and rationale maintenance
downstream design ../../agents/skills/structure-planning.md consumes structure and visualization activation rationale
downstream design ../../agents/skills/report-writing.md consumes report semantics and finding-closure rationale
downstream design ../../agents/skills/test-design.md consumes regression-test admission rationale
downstream design ../../agents/skills/change-review.md consumes durable-finding escalation and OOP-review rationale
downstream design ../../agents/skills/python-review.md consumes Python readability and OOP-review activation rationale
downstream design ../../agents/skills/pr-processing.md consumes queue-planning activation rationale
downstream design ../../agents/skills/html-output.md consumes HTML artifact-versus-serving boundary
downstream design ../../agents/skills/structure-refactor.md consumes drift-repair and review-scope rationale
downstream design ../../agents/skills/task-routing.md consumes routing-state rationale
@dependency-end
-->

## Purpose

This document is the canonical owner for why a reusable AgentCanon mechanism exists and for the narrow condition under which that responsibility should activate. It deliberately does not own one-off simplification decisions: an Issue or PR may explain why a mechanism is reduced for a particular change, while this document keeps the long-lived safety or correctness reason for the responsibility that remains.

The common rule is reachability: a responsibility is selected only when the changed or requested behavior can reach the failure mode that responsibility prevents. Absence of selection is not itself an artifact, receipt, or validation result.

## Skill procedure derivation

When creating, changing, or reviewing a skill procedure, read this contract and
the affected decisions in that skill's owning design. Preserve the correspondence
**shared principle -> skill-specific decision under stated assumptions -> concrete
procedure**. [PHILOSOPHY](../../PHILOSOPHY.md) owns common principles;
[engineering principles](../conventions/software-engineering-principles.md) owns
their decision precedence. Reference the applicable principles rather than copying
them, and treat the latest agreed user requirements as design inputs.

Keep each current decision in its existing responsibility-owned design document
or design section. A link to general philosophy alone does not explain a procedure:
record how the selected criterion applies to this skill and link the affected
procedure sections. The procedure links back to that rationale for authoring and
review. An independently owned design gap may need its own document; every skill
does not need a new file, registry, or record schema.

| Design question | Information to preserve |
| --- | --- |
| What must this skill achieve? | Purpose, inputs, assumptions, scope, and required guarantees. |
| Which criteria select the method? | Applicable principle or requirement, its source, and the priority used when criteria conflict. |
| Why these steps? | The decision leading to each material operation, its input-dependent order, branch conditions, and completion evidence. One decision may explain several steps. |
| What supports the choice? | Relevant specifications, engineering arguments, actually considered alternatives and their comparison, and precise verification or failure-evidence references. |
| When should the choice change? | Applicability limits, unresolved assumptions, and premise or requirement changes that trigger reconsideration. |

Explain order through the inputs an earlier operation produces, branches through
their differing premises, and completion through evidence of the required
postconditions. Distinguish reasoned arguments, static inspection, and observed
behavior. Record untested assumptions and unavailable evidence explicitly; do not
invent alternatives, historical intent, or successful tests to fill the record.
When an old rationale is missing, identify the newly justified current decision
as such rather than claiming to have recovered the author's original reasoning.

Update affected rationale, procedure, and verification criteria in the same change.
Review their correspondence and whether the evidence supports the claimed scope;
link existence alone is insufficient. Reuse valid unchanged decisions. Typo or
format-only edits need no new design decision, and a scoped skill change does not
require retrofitting unrelated skills.

The design owns the current justification; Issue/PR discussions and authorized
logs retain history and detailed evidence. Preserve access boundaries rather than
copying private logs into public prose. Runtime instructions retain the inputs,
conditions, actions, and completion checks needed to execute correctly. Ordinary
skill use does not require reading its design history or all upstream principles.

### Skill maintenance derivation

[skill-cleanup](../../agents/skills/skill-cleanup.md#route) keeps a maintained skill
and its distributed view consistent. Its authoring decisions assume one canonical
procedure owner, the existing
[adapter materializer](skill-runtime-shim-materialization.md), and conditional
reading of relevant sections.

| Procedure decision | Criterion and derivation |
| --- | --- |
| Read the affected design before changing a procedure. | A step depends on its purpose and assumptions. The author needs those inputs to preserve a valid decision or revise a changed premise; the agreed target itself is not reopened. |
| Update rationale and procedure before generating their derived view. | Generated identity depends on the final canonical inputs. Generating first would validate an obsolete source, so the existing source-to-readback sequence follows the authored change. |
| Review the changed decision-to-step correspondence alongside selected validation. | Projection equality establishes source/view consistency, not the adequacy of the decision or actual agent behavior. The existing behavioral evaluation owner supplies observations when selected. |

Procedure-only records lose the reason for a choice. Copying the design history
into each runtime skill duplicates ownership and expands execution-time reading.
A separate decision registry adds another synchronization obligation. The selected
existing-design-plus-links approach keeps one current justification and makes its
procedure correspondence inspectable. This is an engineering argument, not a
measured reduction in tokens or behavioral failures.

Revisit the affected decisions when the skill's guarantees, applicable premises,
source ownership, or generation inputs change. The
[authoring and review route](../../agents/skills/skill-cleanup.md#procedure-rationale)
checks this correspondence; [behavioral tuning](../../agents/skills/skill-cleanup.md#behavioral-tuning)
retains its existing evaluation conditions. Change-specific observations and
unverified results belong in the linked Issue/PR evidence.

## Validation selection and remote execution

Changed paths, operation mode, and repository profile select semantic validation responsibilities once. Focused PR validation exists to distinguish the changed contract from a regression; repository-wide/full-confidence validation exists for cross-surface integration, manual acceptance, and mainline confidence. Remote GitHub Actions exist to replay the selected responsibility in a clean environment, not to add an independent path classifier or to execute unrelated toolchains.

Diagnostic products such as runtime dashboards aggregate evidence that a single PR cannot observe. They therefore belong to schedule/manual diagnostics unless their own schema or generator is changed. Local deterministic classifiers belong to local/unit validation unless a remote environment adds an observable contract.

## Issue and mirror responsibility

Durable issue publication exists so a blocking or recurrent finding that cannot be closed in the current change is not lost when review ends. A finding should be promoted to a durable issue only when it is outside the current owner/scope, recurs, needs later work, or otherwise outlives the review. Findings fixed in the current diff, rejected hypotheses, and ordinary review questions do not require issue lifecycle state.

Local issue/schema validation and remote GitHub reconciliation are separate responsibilities. Remote mirror reconciliation belongs to publication/main/manual synchronization where remote state matters; unrelated PRs should not require authenticated remote reconciliation.

## Structure planning and visualization

Structure planning exists when owner, reader route, source of truth, split/merge boundary, or validation topology is genuinely undecided. A bounded edit inside an already-decided topology does not require a structure packet or a negative `skipped` receipt.

Visualization exists when a diagram materially reduces ambiguity in state, ownership, dependency, or many-to-many flow. Mermaid is an available representation, not a default tax on every nontrivial paragraph or process. Text or a table is sufficient when it represents the relation unambiguously; only selected diagrams require render/readback validation.

Semantic-index and prose-graph tools are diagnostics for unresolved reader-flow hypotheses. They are not default acceptance gates for paragraph ordering, routine README edits, or every structure change.

## Experiment and object-design responsibility

Experiment correctness is primarily hypothesis, inputs, method, environment, metrics, outputs, and reproducibility. OOP responsibility mapping is selected only when stateful objects, plugin/factory boundaries, mutation ownership, or dependency direction are part of the experiment's risk. Pure numerical functions, scripts, and simple benchmarks do not need an invented object model.

Experiment run identity/state has one owner: the experiment lifecycle. Result artifact identity, checksum, and role have one artifact owner. Reporting and publication are optional consumers chosen by the requested operation; wrappers must not re-own the same run state or force producer-specific artifacts that were never generated.

## Report writing and finding closure

A report exists to connect reader-relevant claims to evidence while separating observations, inferences, material limitations, and next actions. These are semantic obligations, not a fixed heading count. Compact reports may satisfy them with paragraphs or tables; external/audit reports may choose stronger structure when the reader contract requires it.

A report may close when accepted blocking findings are zero. Style/advisory findings, demonstrated false positives, and explicitly out-of-scope findings may remain with a short reason. Checker convergence to an empty raw finding set is not the termination predicate.

## Test design

A regression test must identify the contract/behavior under test, a reachable counterexample or already-reproduced failure, and a stable decidable oracle. Additional mechanism traces are useful when the case is ambiguous or algorithmically complex, but fixed five-stage provenance fields are not required for every test.

An existing public failing input or reproduction is itself reachability evidence. A separate null-hypothesis packet is needed only when reachability is genuinely unresolved.

## Review, Python readability, and OOP/SOLID

Review findings are classified by severity, reachability, evidence, and resolution. Durable issue routing is independent from whether a row is a valid review finding.

OOP/SOLID review exists when inheritance/substitutability, dependency inversion, responsibility ownership, or a public object model changes. A Python class/dataclass/type annotation alone is not sufficient activation evidence. Python readability findings are blocking only when they expose concrete maintenance or dependency failures such as cycles, duplicated ownership, or public/private ambiguity; helper physical ordering is guidance, not an API/correctness gate.

## PR queue planning and agent topology

Queue snapshots and dependency DAGs exist when multiple PRs/issues interact through source→pin order, conflict order, or publication dependencies. A single independent PR needs only its own base/head/diff/check/authority state.

Multi-agent execution starts with one owner and expands only when independent search surfaces, competing hypotheses, material verification value, or parallel gain justify it. Fixed scout/verifier/arbiter counts are not a default topology; expansion and stopping depend on marginal information gain, latency/budget, and write contention.

## Write controls

Write safeguards are selected from operation properties. Local/reversible writes may proceed without ceremonial two-phase commit. Bounded remote/reconcilable writes require fresh identity, authority, preconditions, and readback appropriate to the API. Irreversible, high-impact, destructive, or shared-mutable writes require stronger controls such as explicit approval, conflict prevention, or single-writer ownership. Do not emulate unsupported transaction phases merely to produce receipts.

## HTML artifact and serving boundary

HTML output owns the artifact and validation needed to ensure the reader can open and interpret it. Starting an HTTP server, binding a port, and publishing a local/external URL are delivery operations and occur only when preview/serve/publication is explicitly requested. Closeout evidence records artifact identity, provenance, and selected validation; optional operations are recorded only when actually performed.

## Routing state

Task routing has one authoritative selected-skill set plus evidence-backed deferred candidates. Historical aliases may be compatibility reads, but new consumers must not treat ACTIVE/DEFERRED/MATCHED/RELATED variants as independent sources of truth. Candidates do not execute until their activation evidence is satisfied.

## Structure repair and review scope

Known deterministic drift with a known owner, expected state, canonical repair command, and readback is state reconciliation: detect, repair, read back, resume. Full structure planning is reserved for ambiguous ownership, mixed sources, overlapping scope, or multiple plausible target layouts.

Structure review follows the reachable responsibility boundary: changed subtree, direct consumers/reverse edges, and the affected owner boundary. Recursive full-tree evidence is selected for root ownership changes, broad moves, or concrete overlap/uncovered-path evidence. Routine README/path/link changes do not require prose-graph execution unless direct review leaves a specific reader-flow hypothesis unresolved.

## Coordination and runtime bundles

Run bundles exist for work that genuinely needs role/write-scope coordination across multiple owners or shared mutable state. Bundle bootstrap is a local explicit operation. A remote workflow that only creates and uploads a bundle does not by itself constitute multi-agent coordination.
