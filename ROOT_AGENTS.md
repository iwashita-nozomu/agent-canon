# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the common, source-free base for consumer and source-specific repository root AGENTS.md files.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and common/source composition boundary
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
downstream implementation tools/agent/templates/entrypoint_composer.py composes the regular consumer root file
downstream implementation tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates the base grammar
@dependency-end
-->

This common base supplies shared entry behavior for consumer and source-specific
repository roots. It does not own task procedures, command recipes, role
lifecycles, implementation policy, validation schemas, or source-editing policy.

## Repository Role

A consumer owns its product source, build environment, tests, documentation,
CI, credentials, runtime semantics, and instruction extension. Its root
[AGENTS.md](AGENTS.md) is a regular tracked file composed from this base and its own
specific instructions, usable without an AgentCanon checkout or runtime.
Composition is not a live projection, runtime import, updater, vendor checkout,
submodule, or symlink.

The AgentCanon source checkout owns its source and canonical owner map. Its
source-specific [AGENTS.md](AGENTS.md) takes precedence for those responsibilities;
this base's consumer maps and routes do not redirect source work. Details stay
with the applicable repository's specific instructions and canonical owners.

## Reader Map

For a consumer root, use the [Runtime Owner Map](#runtime-owner-map) below and
the appended consumer-specific instructions. For a source-specific root, use
that checkout's [AGENTS.md](AGENTS.md) Reader Map and canonical owners.

## Always-On Boundary

The explicit user request and the current repository-specific canonical owner
are the source of truth. Preserve unknown dirty, staged, untracked, branch,
and worktree state until the applicable Git safety owner classifies it.

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

Do not add exact version pins, hard-coded commit SHAs, or SHA-equality guards
merely for precaution or generic claims of reproducibility. Use the repository's
existing dependency declarations and native resolution mechanism. A new exact
constraint needs an explicit requirement or a demonstrated compatibility,
integrity, or reproducibility need; keep it at the dependency owner rather than
copying it into code or tests. Preserve existing required lockfiles, gitlinks,
and integrity checks. Recording the actual resolved version or SHA is evidence,
not authorization to turn that observation into a permanent execution constraint.

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

Run the current repository owner's existing entrypoint with its configured
settings and standard tool defaults. Manual environment selection for ordinary
execution is prohibited: do not ask the user to choose an environment or inject
host/container, OS/WSL, CPU/GPU backend, runtime, or profile selectors through
ad-hoc command flags, environment variables, or configuration edits. Existing
tools resolve their own configured settings and defaults; missing optional
selectors are not inputs to solicit or fill.
Do not insert environment classification, inventory, or rediscovery before
ordinary tasks, sessions, or commands, including installed-tool probes. Reuse
supplied, still-applicable context without repeating probes or confirmation.
A new task or an unknown optional setting is not a reason to investigate, stop,
reconfigure, or restart a working route. Do not replace manual selection with
new auto-detection, flags, profiles, environment variables, fallbacks, wrappers,
or persistent detection/cache state. Do not invent missing settings merely to
normalize environments or avoid rediscovery.
Environment diagnosis is limited to an explicit request, an actual relevant
failure, an observed change to a required premise, or a concrete evidenced
risk. Resolve only the missing decision-relevant fact and stop the diagnosis
when it is resolved; diagnosis alone does not authorize setup or repair.
Environment changes and their rebuild/full-profile acceptance must belong to
the authorized task, not become prerequisites for ordinary execution.
Preserve the selected command's required safety checks, permissions, resource
limits, and rerun prohibitions; prior success does not override contrary
current evidence. When blocked, identify the concrete prerequisite or risk and
its evidence, stop only affected commands, and continue independent authorized
work. Do not silently switch a required backend, weaken validation, or treat
an unrun command as passed.

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

An observed runtime failure of an AgentCanon-owned invariant is reportable in
the same task as the observation. The first record does not wait for a repeated
occurrence, dashboard evidence, repair completion, or confirmed cause; preserve
the error, command or action, snapshot, expected behavior, actual behavior, and
any unresolved hypotheses through the applicable Issue owner. Generic host,
dotfile, credential, consumer, or ownership-unknown failures stay with their
applicable owner or qualified handoff and are not attributed to AgentCanon by
proximity. This common base exposes that reporting scope without selecting an
external checkout, credential, or publication implementation.

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

Establish the actual working directory and Git root, branch, and `HEAD`, then
trace the selected owner's dependency and consumer edges. At each existing branch/checkout readback
boundary, include the actual clones under the task's `workspace/<...>`, not
only the parent checkout or its declared pins. For each in-scope dependency,
inspect its resolved path, repository identity, branch or detached state,
actual `HEAD`, dirty state, and declared pin against the source actually read
by the selected build/import/execution route. A dependency development clone
and the consumer's pinned checkout are distinct observations; a named path is
only a candidate until that trace confirms the responsible replaceable unit.
Record no dependency only after the trace shows that no edge applies, never
from an unperformed inspection. Re-read the affected identity and dependency
state after a directory, branch, dependency checkout, PR revision, pin, or
source-resolution change; unchanged ordinary commands do not require duplicate
readback. If the consumer's existing dependency contract requires an exact pin,
execution that needs a dependency change uses a published PR commit through
that consumer-owned pin before it runs. Otherwise use the consumer's declared
resolution and record the actual input; do not introduce a pin or a SHA check
to follow this workflow. Dependency-local development validation remains
separate from consumer validation, and an unpinned run must not be reported as
pinned-input verification. Preserve mismatched or unknown checkouts and do not
treat their unverified input as the declared pin. This does not introduce an
AgentCanon dependency into a source-free consumer.

When a task-owned temporary clone is no longer needed, use the applicable
repository cleanup owner immediately rather than waiting for task or PR closeout.
First establish that no active work depends on it and no unpreserved local state
would be lost; unknown or user-owned clones remain untouched. Record removal
or the specific retention reason in the existing task result. This is checkout
cleanup, not authorization to delete remote branches or a shared workspace.

Before a branch or annex operation, read the applicable repository's branch and
storage owners. Keep Git branch metadata and any annex payload as separate
concerns, and let those owners authorize data operations. This common base
defines the read edge only; it does not name a source-repository path or
prescribe an annex command, so a generated consumer root remains self-contained.

Before forming, changing, or delegating a team, read the applicable repository
team owner and the selected orchestration skill, then follow the selected typed
route's definitions for logical role, model/profile, skills, authority, and
handoff. Candidate role lists are not activation instructions, and logical-role
coverage is not a physical-instance count. Keep consumer-owned team guidance
self-contained; a source-specific checkout may name its canonical AgentCanon
team owners, but a consumer root must not import or copy those source paths.

## Runtime Owner Map

For a consumer root, use only the following consumer-owned map:

| Responsibility | Consumer-root canonical owner | Validation / reader route |
| --- | --- | --- |
| product implementation and behavior | consumer source and design owners | consumer implementation route |
| build, tests, and runtime environment | consumer build and test owners | consumer execution route |
| repository structure and file placement | consumer structure owner | consumer structure route |
| root instruction extension | consumer-specific section in this file | consumer instruction route |
| AgentCanon source maintenance (consumer roots) | selected AgentCanon development checkout | AgentCanon maintenance route |
| observed AgentCanon runtime defect | applicable repository-specific Issue owner | immediate Issue record or qualified no-mutation handoff |

## Task Entry

Resolve the task owner and validation oracle through the applicable Reader Map.
For AgentCanon changes from a consumer root, select a separate qualified
AgentCanon development checkout. Keep consumer trees unchanged unless the
consumer task explicitly owns the resulting generated file.

When a root [AGENTS.md](AGENTS.md) begins with the literal `@ROOT_AGENTS.md`, read this
common base first and then continue into that file's source- or consumer-specific
Reader Map. The marker is a reference for the reader, not a claim of automatic
expansion or runtime import.

A progress update is not a final report. Keep the request active while required
implementation, validation, integration, publication, cleanup, or its result
remains unresolved. An acknowledgement, apology, promise, child claim/handoff,
post-hoc healthy status, or incomplete result is not the requested operation or
its success. Preserve the request-to-actual-operation-to-result chain; after a
failure or incomplete result, the responsible owner continues with the next
safe authorized recovery or readback operation, without repeating an already
sufficient operation. If no such operation is authorized or possible, keep the
task non-terminal and report the concrete authority or external blocker with
its evidence and next owner/action. This does not require infinite retries or a
second completion state machine.

A result report leads with the answer to the user's request, not an inventory
of work. Explain whether the goal was met or what the investigation establishes,
what changed relative to the relevant baseline, and why that matters for the
user's use or decision. Connect decisive evidence to the conclusion and explain
what it proves and does not prove; file lists, command success, test counts,
status labels, and PR links are supporting details, not the answer. Distinguish
observations from inference and implemented, verified, published, and applied
states. State material uncertainty or remaining work and how it limits the
conclusion or safe use; do not claim unmeasured benefits. When a user decision is
needed, give the concrete choice, recommended option, rationale, and material
tradeoffs. When none is needed, say so rather than inventing a follow-up or
returning unfinished in-scope work to the user. For Issue-backed work, preserve
comparable rationale, evidence, limitations, and any next owner/action in the
existing Issue comment; links support rather than replace the chat conclusion.
Use the applicable reporting owner for details, without adding fixed headings,
minimum length, empty fields, or a separate reporting gate.

At each coherent work boundary in a repository-changing task, decide whether
to commit and whether to push as separate operations. Commit a coherent,
reviewed unit after the selected validation when the request and ownership
support it; if the work is incomplete or mixes user-owned changes,
preserve it and state the concrete reason and next condition in the existing
work log or final status. Decide push independently from its sharing,
handoff, remote-backup, or PR purpose, the existing authority, and the
designated destination. Read-only, local-only, no-push, no-change, and genuine
external-failure cases remain valid. Do not force-push, mutate `main`, overwrite
unknown user files, create a new remote, or merge across scope. A committed but
unpushed child result is an intermediate handoff, not final publication; the
next authorized owner must launch the selected push operation when its purpose
and conditions are met. This is decision guidance, not an unconditional
commit/push gate or a new receipt requirement.

## Validation Routing

Use the validation route owned by the changed repository-specific responsibility.
Formatting is part of completing edits, not an optional repair after lint fails.
Before final validation, staging, and commit or handoff, run the repository's
configured formatter on the task's edited files and review and include its diff.
Repeat after later edits, generation, fixers, or conflict resolution; an earlier
result does not cover changed content. A combined command that actually formats
the final files satisfies this step; tests or check-only lint do not. Preserve
unrelated or user-owned changes and the repository's existing formatting scope.
Do not add a formatter, configuration, hook, environment probe, or repository-wide
reformat to satisfy this rule. If no formatter is configured, do not invent one.
If the selected formatter fails or cannot run, record the command, affected files,
and reason in the existing Issue / PR or task result; hand off as unverified,
not as formatting-complete.

Validate the changed contract and its failure semantics, then use that owner's
closeout route when required. A generated consumer root file does not authorize
unrelated AgentCanon checks, product checks, or runtime changes.
