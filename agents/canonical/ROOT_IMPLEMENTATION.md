# Implementation decisions

<!--
@dependency-start
contract agent-runtime
responsibility Owns detailed source-side implementation and numerical decision guidance.
upstream design ../../AGENTS.md conditional source reader map
upstream design ../../ROOT_AGENTS.md portable common boundaries
upstream design ../../documents/design/entrypoint-owner-map.md source and consumer split contract
upstream design ../../documents/design/api-surface-traversal-policy.md traversal and API change rationale
upstream design ../../documents/conventions/software-engineering-principles.md maintained code-space objective, abstraction admission, and reuse feasibility decision owner
upstream design ../../documents/design/responsibility-cleanup.md replacement retirement and necessary consumer migration
upstream design ../../documents/operations/notes-lifecycle.md failed verification recording and reuse
@dependency-end
-->

Read the section selected by the source [AGENTS.md](../../AGENTS.md) Reader Map
when its responsibility is active. This is source-side detail, not an
additional startup packet or a dependency of generated consumer instructions.

## Contract and valid domain

Use [SEP-01](../../documents/conventions/software-engineering-principles.md#sep-01-contract-first)
to distinguish required problem semantics from changeable design contracts.
API shape, representation, internal preconditions, state transitions, and ownership
are candidates for redesign, not immutable constraints merely because code, tests,
or documentation already prescribe them. Compare contract-and-implementation pairs
before choosing the simplest design, with preserved requirements, intended semantic
changes, and necessary consumer migration explicit. Do not require equivalence to
obsolete behavior that the authorized change is meant to correct.

Keep the required input domain, output, safety, performance, and failure guarantees.
Do not turn a method's limitations into stronger user preconditions, silently skip
valid cases, or weaken guarantees to make implementation or proof easier. A changed
internal precondition needs a derivation showing how every required input reaches
it legally. A real conflict with explicit compatibility or authority needs the
exact affected requirement and decision, not a blanket contract-preservation veto.

## Simplest complete implementation

Use [SEP-01](../../documents/conventions/software-engineering-principles.md#sep-01-contract-first)
to align the owning design with the latest explicit agreement before choosing a
mechanism. State the required outcome, valid inputs, guarantees, and completion
evidence first. Carry source-backed constraints with the affected operation.

Apply [SEP-06](../../documents/conventions/software-engineering-principles.md#sep-06-kiss)
per responsibility: compose existing capabilities for new functionality; reconsider
structure preservation for repairs. Use [reuse feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
to inspect abstractions, actual callers, APIs, configuration, dependencies, and
extension points before implementation. Follow its investigation-to-verdict sequence:
check the concrete use, settle the material requirement, and state the evidence-backed
adoption, correction, or rejection. Search prior failed attempts through
[Notes Lifecycle](../../documents/operations/notes-lifecycle.md#retrieve-before-deciding),
reuse results under matching premises, and verify decision-relevant changed premises.

Within that starting point, apply SEP-06's mathematical simplicity comparison,
including contract redesign, independent state, exceptional cases, coupled
invariants, and proof obligations across the affected unit and its consumers.
Before selecting a repair, use [SEP-07 Reachability and remedy necessity](../../documents/conventions/software-engineering-principles.md#reachability-and-remedy-necessity)
to establish that the current implementation fails a required contract and that
existing guarantees do not already satisfy it.
Remove redundant representations and mechanisms when the derivation permits.
Consolidate the root responsibility and trace affected contracts to consumers;
use that complete unit to determine the change scope. For repairs, correct the
existing owner's mechanism rather than adding a specialized branch; preserve
verified distinctions required by domain behavior or input contracts. Reuse sound
parts and retire superseded branches together with the common correction.

For replacement or retirement, close [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
in the same change: remove obsolete paths and support, migrate affected uses, and
validate agreed behavior rather than freezing superseded implementation in tests.
Review the completed unit, including retained code, not just the diff. Record
material reductions and necessary growth in the existing design/PR rationale;
line compression, relocation, and deletion quotas are not evidence of improvement.
Preserve required domain, correctness, safety, performance, failure semantics, and
behavior-preserving refactor contracts. Add no unrelated cleanup, checker, report,
or approval gate.

Before implementing, derive the selected contract's obligations through
[SEP-11](../../documents/conventions/software-engineering-principles.md#sep-11-testability-and-validation-selection).
Connect assumptions, invariants, transitions, and required termination to actual
paths/symbols; derive tests from those properties and remaining execution risks.
Discharge decision-relevant obligations by checking the derivation, its premises,
and actual code, and executing the necessary focused checks. Close gaps in the same
task with the next relevant investigation or verification. Record failed checks in
the owning topic with their reproduction conditions and verified conclusions.

## Public API additions

A requested fix covers necessary replacement, removal, signature changes, unavoidable
additions, and affected consumer migration. Resolve concrete compatibility or
authority conflicts through the existing owner routes while correcting the root
contract.

Before implementation, use [API surface traversal](../../documents/design/api-surface-traversal-policy.md)
to inspect current abstractions, real callers, APIs, configuration, extension
points, standard facilities, and adopted dependencies. New functionality starts
with direct use or composition before a new API. Keep one exposed API per
functional capability. Alternate names or routes, forwarding aliases, independent
duplicate APIs, and compatibility wrappers are additional APIs for that capability.
Private implementation decomposition is not an API; preserve distinct
responsibilities. Use existing domain types, API contracts, and responsibility
abstractions for structural guarantees; keep workflow guidance with its owner
instead of encoding it wholesale in flags, validators, or runtime admission
gates. Validate real untrusted input and I/O at their boundary, but do not repeat
guards for invariants already enforced by a type or API. For a repair, choose the
simplest complete correction, including replacement when justified. Test a
concrete candidate use against the required property, including relevant
configuration and composition.
State the checked input/source, actual result, and conclusion; investigate a missing
guarantee until the material decision is settled. Record candidates, verified unmet
contracts, and necessary owner/API changes in the existing design.

Fix the root, then trace references and actual callers through the existing
dependency or LSP owner against the required contract. Use or migrate affected
implementations, tests, and documentation to the existing/latest canonical API
in the same change; stop tracing at unchanged contracts, not at the originally
named files. Validate required semantics and the corrected public contract; do
not freeze defective behavior in tests or move the defect into caller workarounds.
Retire duplicate/obsolete entrypoints and exclusive support in the same change.

Keep existing safety, access, and publication authority. A concrete conflict
with an explicit compatibility constraint or unavailable consumer write access
requires an exact affected contract, unfinished migration, and next owner/action,
not a generic API-preservation veto. Continue independent authorized work.
Unrelated API additions still need explicit authorization. Keep these decisions
with existing design, implementation, and review owners; add no checker,
registry, mandatory report, or separate approval system.

## Necessity in durable design

Whenever adding or changing code or an API, always keep the necessity rationale
in the responsible repository's durable design document, not only in task
records. Explain the concrete requirement and caller/consumer, what would remain
unmet without the code/API, and the mathematical or engineering grounds and
assumptions for the chosen approach. Compare direct use or composition of
existing APIs and simpler alternatives; justify any additional mechanism only
by the remaining gap. Support each material rejection with the checked condition,
verification method, actual result, and the unmet requirement. Apply the conclusion
to the verified scope and link the reusable failed-verification topic.
For removals, explain which mechanism meets the requirement or why it is retired.
Establish the rationale before implementation and keep it aligned with the
change in the same PR. Connect its design section to the relevant implementation
paths/symbols at responsibility-unit granularity. Reuse an adequate, still-current
design explanation by reference instead of copying it for each function or edit;
add or update a concise section under existing design conventions when needed.
Record the latest explicit agreement in that section before editing; its older
text must not override the agreement. Chat, Issue/PR discussion, and code comments
may support or link to the rationale but do not replace the durable explanation.
At nonobvious code boundaries, keep the local necessity, guaranteed behavior or
effect boundary, and owning responsibility readable with concise comments or
docstrings; link the actual design owner where useful. Do not restate symbol names
or invent rationale, and do not require a comment for every line or function. If
necessity or ownership cannot be explained from evidence, investigate or
reconsider the implementation instead of writing a comment to bless it. Use the
existing design and review owners; do not add a checker, schema, approval gate,
or unrelated retrospective documentation task.

## Dependency constraints

Do not add exact version pins, hard-coded commit SHAs, or SHA-equality guards
merely for precaution or generic claims of reproducibility. Use the repository's
existing dependency declarations and native resolution mechanism. A new exact
constraint needs an explicit requirement or a demonstrated compatibility,
integrity, or reproducibility need; keep it at the dependency owner rather than
copying it into code or tests. Preserve existing required lockfiles, gitlinks,
and integrity checks. Recording the actual resolved version or SHA is evidence,
not authorization to turn that observation into a permanent execution constraint.

## Reachable abnormal conditions

Before implementing a guard, retry, fallback, or other abnormal-condition
handling, determine the required failure behavior and triggering input/state.
Trace the supported entrypoint, governing specification, maintained invariants,
and actual control/data flow. Verify whether the condition is reachable and
whether existing rejection, propagation, cleanup, or recovery meets the requirement.
Investigate a missing premise and perform the focused check needed to settle that
judgment. Specifications and sound analysis can establish a possible failure without
an unsafe reproduction. Preserve required authorization and external-boundary checks.

Choose the simplest remedy for the demonstrated gap at its owner and verify the
identified condition. Use the governing capability contract for guards; keep
portability and reuse across supported environments. Reuse guarantees already
maintained at the same trust boundary. Record the triggering condition, existing
guarantee, checked result, and selected action in the existing design or Issue;
persist a failed check through the existing topic-note/log owner.

## Algorithm-first numerical diagnosis

When numerical results disagree, first investigate defects in the algorithm
and its implementation against the governing equations and specification,
including assumptions, units, indexing, update order, and boundary conditions.
Correct identified algorithmic defects before considering numerical adjustments.
Do not hide unexplained discrepancies with correction factors, offsets,
clipping, arbitrary epsilons, or relaxed test tolerances. Numerical remedies
are justified only after algorithmic correctness has been checked and the
remaining discrepancy is attributable to rounding, conditioning, or
approximation, with an error analysis and validation against an independent
reference or invariant. Keep the investigation and validation with the
applicable repository's algorithm and numerical owners.

## Numerical result retention

Report numerical concerns and interpretation limits honestly; do not hide failures
or present invalid results as success. Numerical symptoms alone are not a
universal research-failure judgment. Preserve non-experiment results and
experiment observations whose failure has not been established by the applicable
topic protocol and evidence; do not introduce an automatic numerical discard gate.
For a confirmed failed experiment, immediately delete its experiment-only code,
configuration, and artifacts unless evidence establishes physical properties as
the cause. Unknown cause, numerical or implementation trouble, debugging value,
and possible future reuse do not justify retention or waiting for task/PR closeout.
Apply this disposition through the existing experiment lifecycle and artifact
owners; a generic preserve-results or append-only rule must not override it.
Retain the concise failure, reproduction conditions, verified conclusion, and
reuse conditions in the existing topic memo or authorized log. Link the deletion
or physical-retention disposition from the Issue/task and preserve that finding
while retiring the failed implementation and experiment-only artifacts.
Do not extend deletion to successful results, shared code, other owners' data,
or Git history. Preserve required safe stopping and scoped deletion authority;
do not add a classifier, checker, archive prerequisite, or rerun to decide cleanup.

## Caller and library responsibility

Before selecting or editing a repository surface, inspect its actual location,
canonical owner, callers, and consumers. For library-backed work, inspect the
caller and the relevant public API, including nested configuration and existing
extension points, before proposing library edits. Trace the required behavior to
the owner that maintains its guarantees: use-case selection, orchestration,
environment setup, and presentation stay with their callers; reusable semantics
stay with the library. Verify the concrete use, including relevant configuration
and composition, to identify an unmet library contract or caller-owned correction.
One valid caller can establish a library defect. Correct that common owner and
migrate its affected uses, then verify both the contract and consumer connection.
Record the owner decision, checked result, and verified alternative comparison
in the existing design/PR rationale, referencing reusable failure evidence.
