# Implementation decisions

<!--
@dependency-start
contract agent-runtime
responsibility Owns detailed source-side implementation and numerical decision guidance.
upstream design ../../AGENTS.md conditional source reader map
upstream design ../../ROOT_AGENTS.md portable common boundaries
upstream design ../../documents/design/entrypoint-owner-map.md source and consumer split contract
@dependency-end
-->

Read the section selected by the source [AGENTS.md](../../AGENTS.md) Reader Map
when its responsibility is active. This is source-side detail, not an
additional startup packet or a dependency of generated consumer instructions.

## Contract and valid domain

Preserve the problem class, valid input domain, and output guarantees required
by the explicit user request and applicable canonical contract. A bounded
change scope is not permission to narrow that problem. Do not add fixed
dimensions, shapes, distributions, or other preconditions merely to fit a
chosen algorithm, library, test fixture, implementation convenience, or
performance target. Distinguish restrictions inherent in the governing problem
from limitations of the chosen method; choose or derive a suitable method
instead of promoting the latter into the specification. Do not reject or skip
valid cases, or silently truncate or project them into a different problem,
and call the result complete. Unresolved coverage remains an implementation
gap, not invalid input or authorization to shrink the contract. Narrowing
requires explicit user direction. Validate through the applicable implementation
and test owners, including valid cases beyond the motivating example and cases
a shortcut would exclude.

## Simplest complete implementation

Make the simplest complete implementation the default, not a later refactor.
Start with direct use or composition of existing APIs and straightforward code
at the current owner. Introduce abstractions, configuration, execution paths,
or state only when a concrete current requirement cannot be met more simply;
justify that necessity with mathematical or engineering grounds. Hypothetical
reuse, design-pattern uniformity, or test-double convenience alone is not such
a reason. Minimize concepts, state, branches, and dependencies while preserving
the required domain, correctness, safety, and failure semantics. Neither fewer
lines nor a smaller diff justifies omitted behavior, and completeness does not
authorize speculative generalization or unrelated library or consumer changes.
Keep the decision with the existing implementation and review owners, without
adding a checker, report, or approval gate to enforce simplicity.

## Necessity in durable design

Whenever adding or changing code or an API, always keep the necessity rationale
in the responsible repository's durable design document, not only in task
records. Explain the concrete requirement and caller/consumer, what would remain
unmet without the code/API, and the mathematical or engineering grounds and
assumptions for the chosen approach. Compare direct use or composition of
existing APIs and simpler alternatives; justify any additional mechanism only
by the remaining gap. A behavior description, signature, or generic claim of
future usefulness or safety is not a necessity rationale. For removals, explain
why it is no longer needed or which mechanism now meets the requirement.
Establish the rationale before implementation and keep it aligned with the
change in the same PR. Connect its design section to the relevant implementation
paths/symbols at responsibility-unit granularity. Reuse an adequate, still-current
design explanation by reference instead of copying it for each function or edit;
add or update a concise section under existing design conventions when needed.
Chat, Issue/PR discussion, and code comments may support or link to that section
but never replace its explanation. If necessity cannot be justified, reconsider
the implementation rather than inventing a reason. Use the existing design and
review owners; do not add a checker, schema, approval gate, or unrelated
retrospective documentation task.

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
handling, first determine whether the condition can occur under the current
contract and supported execution environment. Identify the triggering
input/state and assess reachability from observations, specifications, code,
or mathematical and engineering analysis. Distinguish established possibility,
exclusion by maintained invariants, and unresolved uncertainty. Absence of
incidents does not prove impossibility; a hypothetical failure alone does not
establish reachability. Do not add handling for excluded conditions or turn
uncertainty into speculative production code; investigate the missing premise
first. Preventive handling does not require a real incident or unsafe
reproduction when specifications or analysis establish possibility. Only after
that judgment, use impact and existing guarantees to select the smallest
necessary remedy at the responsible owner and validate it against the
identified condition. Do not make guards or preflight checks stricter than the
governing contract: avoid environment, directory-layout, or exact-version
restrictions when the required capability suffices, and repeated checks of
invariants already guaranteed at the same trust boundary. An unavailable
optional tool or diagnostic must not block an otherwise supported path.
Validate untrusted inputs at the owning boundary rather than coupling reusable
code to one caller's setup. Prefer no new check unless it closes an evidenced
gap without unnecessarily reducing portability or reuse. Preserve required
authorization, safety, and external-boundary checks; do not suppress their
failures. Record the judgment and grounds in the existing Issue or design record,
not a new gate or report.

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
Keep only a concise failure, cause/evidence, and deletion or physical-retention
record in the existing Issue or task record, not a relocated experiment bundle.
Do not extend deletion to successful results, shared code, other owners' data,
or Git history. Preserve required safe stopping and scoped deletion authority;
do not add a classifier, checker, archive prerequisite, or rerun to decide cleanup.

## Caller and library responsibility

Before selecting or editing a repository surface, inspect its actual location,
canonical owner, callers, and consumers. For library-backed work, inspect the
caller and the relevant public API, including nested configuration and existing
extension points, before proposing library edits. Distinguish a caller's
convenience gap from a defect or missing capability in the library's own
contract. Keep use-case selection, orchestration, environment setup, and
presentation with their owning callers; do not move them into a reusable core
merely to shorten a caller, remove textual duplication, or anticipate future
reuse. Change a library only when the required behavior belongs to its
abstraction and an evidenced contract defect or capability gap requires it,
within the authorized scope. One valid caller can demonstrate a library defect;
do not hide it in a caller workaround or require multiple callers for a
correctness fix. Prefer direct use or composition of existing APIs when
sufficient, without adding an unnecessary wrapper, helper, mode, or
generalization layer. Record the owner choice and rejected alternative in the
existing Issue / PR rationale, not a new gate or report.
