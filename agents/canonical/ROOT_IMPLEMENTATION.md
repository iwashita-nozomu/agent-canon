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
upstream design ../../documents/notes/knowledge/unix-linux-philosophy.md primary-source rationale and limits for composable boundaries
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

 Before implementation, use the existing
 [reuse feasibility support](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
 to locate abstractions that already own the required behavior. Trace actual
 callers, usage examples, provider dependencies, contracts, configuration, and
 extension points. A failed name search or unfamiliar location does not establish
 absence. Settle direct use, composition, extension at the existing owner, or an
 evidenced responsibility gap before writing code, including private helpers and
 additions inside existing files. Unknown keeps only the affected implementation
 pending; it does not require a repository-wide audit or justify inventing a
 foundation.

 Design for the smallest maintained code space after the change, not the smallest
diff. Apply [SEP-06](../../documents/conventions/software-engineering-principles.md#sep-06-kiss)
to the final implementation, including retained code and support mechanisms.
Start with direct use or composition of existing APIs; admit new abstractions,
configuration, routes, or state only for an evidenced unmet current requirement.
Hypothetical reuse, pattern uniformity, or test-double convenience is not a gap.
Preserve the required domain, correctness, safety, performance, and failure semantics;
code compression or omitted behavior is not simplification.
For replacements, include the retained owner, superseded code, and necessary
consumer migration in the existing design before implementation, then close
[RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
in the same change. Do not defer deletion to a later cleanup or keep the old path
to reduce the diff. Keep unrelated changes out; add no checker, report, or approval
gate to enforce this objective.

When composition, interfaces, policy placement, or resource lifetime changes,
use the applicable decision below. Other edits do not activate all sections or
a fresh philosophy survey. Existing engineering principles remain the general
policy owner; the optional [research note](../../documents/notes/knowledge/unix-linux-philosophy.md)
explains the sources, tradeoffs, and limits rather than adding a second policy.

## Composable interfaces and explicit mechanisms

### Policy, mechanism, and representation

Keep one cohesive responsibility behind a usable contract. Compose the same
existing component in standalone and combined use; do not make a second
implementation for a pipeline or caller variant. Under
[SEP-03 and SEP-05](../../documents/conventions/software-engineering-principles.md),
keep use-case selection, configuration policy, orchestration, and presentation
with the caller, and reusable computation or mechanism with its owner.
Do not split one invariant or atomic operation merely to make smaller files,
functions, or processes; IPC and serialization are costs, not proof of modularity.

Before adding branches or modes, inspect the data representation, valid states,
units, and ownership. Prefer an existing type, standard data structure, or small
table when it removes special cases without hiding different semantics.
A new DSL, schema, interpreter, registry, or generic framework still needs the
existing abstraction-admission evidence. Keep control flow and effects readable;
comments explain non-obvious invariants and reasons, not a paraphrase of each line.

### Program boundaries

For a machine-facing CLI, keep result data on stdout and diagnostics on stderr;
follow an existing protocol's channel contract instead when it specifies another
boundary. Do not mix progress, decoration, or interactive prompts into data.
Provide non-interactive inputs for automated use without bypassing authorization.
Define the applicable input format, encoding, record boundaries, escaping, ordering,
exit-status meanings, and validity of partial output. Reuse established formats,
serializers, parsers, argument APIs, and native tools rather than inventing them.
Do not parse human display output when a supported machine interface suffices,
or interpolate untrusted input into shell command strings.

Use text when it preserves the required interoperability, precision, and cost;
keep typed in-process or binary interfaces when those better satisfy the contract.
Do not force a numerical library through a CLI or convert every value to a string.
A command's quiet success still has defined output and status; failures must remain
observable. A reusable library reports errors through its API, not by unexpectedly
printing to global streams or terminating its caller.

### Streams and owned resources

For streaming or process composition, account for framing, EOF, partial I/O,
backpressure, cancellation, and descriptor ownership where they affect the
changed contract. A byte stream is not a message protocol. Reuse guarantees of
the selected library/runtime rather than rebuilding low-level handling.
Do not assume unlimited buffering or a particular pipe capacity. Streaming is
not mandatory when the operation needs global data; use the supported workload
and existing resource owner to choose storage and processing granularity.
Classify early consumer termination by the command contract: neither suppress
all broken-pipe failures nor assume every deliberate short read is a defect.
Do not impose a blanket signal handler, retry loop, shell option, or preflight.

Give acquired resources an explicit lifetime owner and use the language's native
scoped cleanup where sufficient. Handle partial acquisition, cancellation, and
failure without double release, leaks, hidden shared state, or loss of the first
failure. Close only owned resources; borrowed resources retain their owner's
contract. Validate reachable cleanup paths, using the existing
[reachability and remedy rule](../../documents/conventions/software-engineering-principles.md#reachability-and-remedy-necessity),
not speculative guards or repeated checks already guaranteed by the boundary.

### Compatibility and evidence

Check actual affected workflows, not just unchanged signatures: data meaning,
precision, ordering, status, side effects, and required performance may change
without an API rename. Apply [Public API additions](#public-api-additions) to
necessary changes and migration; public visibility alone is not an API freeze.
Linux's unusually strong user-regression policy is not permission to ignore
undocumented usage, nor a universal ban on authorized internal replacement.

Use the existing [workload and scale decision](../../documents/conventions/software-engineering-principles.md#workload-and-scale-before-mechanism)
for algorithm and resource choices. Support claimed speedups with relevant
measurements; do not demand new benchmarks when existing guarantees or analysis
settle the decision, and do not call unmeasured performance verified.
Review one complete logical change with its necessary callers, tests, and docs;
small patches aid review but do not excuse unfinished migration. Validate the
changed boundaries and observable results, not adherence to slogans or code shape.
Keep rationale and evidence with the existing design/PR, without a new checklist,
checker, report, approval stage, or runtime setup obligation.

## Public API additions

Do not stop a requested fix to preserve an existing API or ask for separate
approval solely because the fix changes its public shape. The request covers
necessary replacement, removal, signature changes, and unavoidable additions,
with affected consumer migration, not unrelated features or speculative exports.
An explicit compatibility requirement remains a constraint; do not invent one
from active use, existing tests, or public visibility.

Before implementation, use [API surface traversal](../../documents/design/api-surface-traversal-policy.md)
to inspect current abstractions, real callers, APIs, configuration, extension
points, standard facilities, and adopted dependencies. Reuse sufficient current
findings; not finding a name or preferring another signature is not a capability
gap. If direct use or composition suffices, use it without a new API. Otherwise,
record the candidates, source evidence, unmet contract, and necessary owner/API
change in the existing design, then implement it within the requested scope.
Unknown capability remains unknown; it neither justifies speculative additions
nor blocks independent authorized work.

Fix the root, then trace references and callers through the existing dependency
or LSP owner and migrate affected implementations, tests, and documentation in
the same change. Stop tracing at unchanged contracts, not at the originally
named files. Validate required semantics and the corrected public contract;
do not freeze defective behavior in tests or move the defect into caller
workarounds. Remove obsolete implementation paths and dedicated support code;
retain a compatibility entrypoint only for an actual required contract and
connect it to the canonical implementation, not a second implementation.

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
