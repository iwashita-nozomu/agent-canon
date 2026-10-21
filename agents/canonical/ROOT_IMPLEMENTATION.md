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
upstream design ../../documents/notes/knowledge/unix-linux-philosophy.md optional primary-source rationale for machine-facing and streaming contract decisions
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

In a design document, bind an implementation condition to an agreed requirement
or a concrete guarantee and explain why that restriction is necessary. Where
multiple implementation choices satisfy the contract, leave private names, layout, and
edit order to the implementation owner. Distinguish requirements from
recommendations and incidental facts of the current implementation.

Keep the required input domain, output, safety, performance, and failure guarantees.
Do not turn a method's limitations into stronger user preconditions, silently skip
valid cases, or weaken guarantees to make implementation or proof easier. A changed
internal precondition needs a derivation showing how every required input reaches
it legally. A real conflict with explicit compatibility or authority needs the
exact affected requirement and decision, not a blanket contract-preservation veto.

## Machine-facing and streaming contracts

When adding or changing a machine-facing command or stream boundary, derive its
I/O contract from actual callers and protocols. Keep machine-readable results
distinguishable from human diagnostics, normally by using stdout for results and
stderr for diagnostics unless the owning interface defines another channel
contract. Specify accepted input mode, record framing, end-of-input, exit status,
and whether an emitted prefix is a valid partial result.

For an actual streaming path, determine how its producer and consumer handle
EOF, a slow or closed consumer, backpressure, and cancellation. Treat partial
writes and early consumer exit according to that contract; do not present
partial output as complete success or silently replace streaming with unbounded
buffering. Apply these stream-specific decisions only when the selected path
actually streams; reuse existing transport/runtime behavior and add no generic
wrapper, buffer limit, or checker.

## Simplest complete implementation

Use [SEP-01](../../documents/conventions/software-engineering-principles.md#sep-01-contract-first)
to align the owning design with the latest agreement. State the required outcome,
valid inputs, and guarantees, then choose the simplest complete mechanism under
[SEP-06](../../documents/conventions/software-engineering-principles.md#sep-06-kiss).

For numerical implementation or tuning, apply
[Before optional changes](../skills/computational-optimization.md#before-optional-changes)
before adding mechanisms beyond the requested method. Establish the actual
baseline first; preserve mathematically required work and explicit execution holds.

For reuse decisions, apply [reuse feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
and reuse established evidence while its premises hold. For repairs, use
[SEP-07 Reachability and remedy necessity](../../documents/conventions/software-engineering-principles.md#reachability-and-remedy-necessity)
to establish the unmet contract, correct its owner, and preserve required domain
and boundary behavior. Do not expand a local repair into unrelated cleanup.

For replacement or retirement, close [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
in the same change: remove obsolete support and migrate uses included in the
change. Preserve required behavior and validate the affected contract; do not
freeze superseded implementation in tests or add unrelated cleanup, checks, or
approval gates.

Before implementing, derive the selected contract's obligations through
[SEP-11](../../documents/conventions/software-engineering-principles.md#sep-11-testability-and-validation-selection).
Reuse established component guarantees as premises when their stated preconditions
hold. Validate the changed responsibility and remaining execution risks, not an
unchanged component's internal property again.

## Public API additions

Use this section for an explicitly requested public API change. Include only the
necessary addition, removal, signature change, and migration in its declared
scope; preserve existing compatibility and authority constraints. Use [API surface
traversal](../../documents/design/api-surface-traversal-policy.md) for the
declared public surface. Prefer direct use or composition before adding an API,
keep one exposed API per capability, and avoid aliases or wrappers. Keep
caller-owned workflow, environment, and presentation outside reusable library
semantics. Validate untrusted input at its boundary without repeating guarantees
already enforced by an API or type. Resolve concrete compatibility or access
conflicts through existing owners; unrelated API additions still need explicit
authorization.

## Necessity in durable design

Keep the concrete requirement, assumptions, and reason for a non-obvious change
in the responsible durable design. Reuse a current explanation by reference;
update it with the implementation when the agreement or mechanism changes. For
removals, state what meets the requirement or why the mechanism is retired. Keep
decisive evidence for material alternatives in the same rationale. Keep comments
concise at boundaries where local necessity or ownership is not otherwise clear.

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

Add abnormal-condition handling only for a required, reachable failure behavior
not already met by an existing guarantee. Put the minimal remedy at its owning
trust boundary, preserving authorization and external behavior. Reuse guarantees
already maintained there.

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

The caller owns use-case selection, orchestration, environment, and presentation;
the library owns reusable semantics. Correct a library only for an unmet shared
contract; a concrete valid use can expose that gap. Keep caller-specific behavior
at its caller. For public API changes, include the uses and migration required by
the declared change.
