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

This is the common base for a repository root [AGENTS.md](AGENTS.md), including a consumer
root and a source-specific AgentCanon root. A consumer keeps its generated file
as a regular tracked file by composing this base with its own specific
instructions. A source-specific AgentCanon [AGENTS.md](AGENTS.md) reads the shared entry
behavior explicitly and retains its own reader map; the consumer-only maps and
routes below do not apply to that source root. These are explicit
reads/composition, not a live projection, runtime import, updater, vendor
checkout, submodule, or symlink.

## Repository Role

For a consumer root, the consumer repository owns its product source, build
environment, tests, documentation, CI, and tracked instruction extension.
AgentCanon does not become a second source of truth for those surfaces. The
generated root file is self-contained after it is committed and remains usable
when the AgentCanon source checkout and runtime are unavailable. For a
source-specific AgentCanon root, the source checkout owns AgentCanon's source
and canonical owner map; its source-specific [AGENTS.md](AGENTS.md) takes precedence for
those responsibilities, while consumer-only guidance below does not redirect
source work.

## Reader Map

For a consumer root, use only the following consumer-owned map:

| Task intent | Applicable reader |
| --- | --- |
| product implementation and behavior | the consumer's source and design owners |
| build, test, and execution environment | the consumer's build and test owners |
| repository structure and file responsibility | the consumer's structure documentation |
| consumer-specific agent instructions | the appended consumer-owned section of this file |
| AgentCanon maintenance (consumer roots) | a separately selected AgentCanon development checkout |
| observed AgentCanon runtime defect | the applicable repository-specific Issue owner | immediate Issue record or qualified no-mutation handoff |

For a source-specific AgentCanon root, the source checkout's [AGENTS.md](AGENTS.md) Reader
Map and canonical owners are the local authority. The common base supplies
shared entry behavior without reassigning source responsibilities.

## Always-On Boundary

The explicit user request and the current repository-specific canonical owner
are the source of truth. Preserve unknown dirty, staged, untracked, branch,
and worktree state until the applicable Git safety owner classifies it. For a
consumer root, keep consumer product behavior, environment policy, tests, CI,
credentials, and runtime semantics with consumer owners. For a
source-specific AgentCanon root, keep those source responsibilities with the
source checkout's owners.

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

This common base establishes the shared root instruction boundary. It does not
re-own task procedures, command recipes, role lifecycles, implementation policy,
validation schemas, or AgentCanon source-editing policy. Consumer details belong
to the consumer-specific section or the consumer's own canonical owner; source
details belong to the source-specific [AGENTS.md](AGENTS.md) and its canonical owners.

Before selecting or editing a repository surface, inspect its actual location,
canonical owner, callers, and consumers. Establish the actual working
directory and Git root, branch, and `HEAD`, then trace the selected owner's
dependency and consumer edges. Inspect the actual `HEAD` of every in-scope
dependency checkout and its pin when present; a named path is only a candidate
until that trace confirms the responsible replaceable unit. Record no dependency
only after the trace shows that no edge applies, never from an unperformed
inspection. Re-read this identity and dependency state after a directory,
branch, dependency checkout, or pin change; unchanged ordinary commands do not
require duplicate readback.

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
| observed AgentCanon runtime defect | applicable repository-specific Issue owner | immediate Issue record or qualified handoff |

For a source-specific AgentCanon root, the source checkout's [AGENTS.md](AGENTS.md) and
its canonical owners supply the owner and validation route.

## Task Entry

Start with this common base and the applicable source- or consumer-specific
instructions. Resolve the task owner and repository-specific validation oracle
from those surfaces. For a consumer root, use its appended consumer-specific
instructions and select a separate qualified AgentCanon development checkout
when the task changes AgentCanon itself. For a source-specific AgentCanon root,
continue with that checkout's [AGENTS.md](AGENTS.md) Reader Map and canonical owner; keep
consumer trees unchanged unless the consumer task explicitly owns the resulting
generated file.

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
Validate the changed contract and its failure semantics, then use the applicable
consumer or source closeout route when required. A generated consumer root file
does not authorize unrelated AgentCanon checks, product checks, or runtime
changes; a source-specific root follows its source owner route.
