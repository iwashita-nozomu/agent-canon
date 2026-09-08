# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the common, source-free base for a consumer repository's generated root AGENTS.md.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and consumer composition boundary
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
downstream implementation tools/agent/templates/entrypoint_composer.py composes the regular consumer root file
downstream implementation tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates the base grammar
@dependency-end
-->

This is the common base for a repository root `AGENTS.md`, including a consumer
root and a source-specific AgentCanon root. A consumer keeps its generated file
as a regular tracked file by composing this base with its own specific
instructions. A source-specific AgentCanon `AGENTS.md` may reference this base
explicitly and retain its own reader map. These are explicit reads/composition,
not a live projection, runtime import, updater, vendor checkout, submodule, or
symlink.

## Repository Role

The consumer repository owns its product source, build environment, tests,
documentation, CI, and tracked instruction extension. AgentCanon does not
become a second source of truth for those surfaces. The generated root file is
self-contained after it is committed and remains usable when the AgentCanon
source checkout and runtime are unavailable.

## Reader Map

| Task intent | Consumer-owned reader |
| --- | --- |
| product implementation and behavior | the consumer's source and design owners |
| build, test, and execution environment | the consumer's build and test owners |
| repository structure and file responsibility | the consumer's structure documentation |
| consumer-specific agent instructions | the appended consumer-owned section of this file |
| AgentCanon maintenance | a separately selected AgentCanon development checkout |

## Always-On Boundary

The explicit user request and the current consumer-owned canonical owner are
the source of truth. Preserve unknown dirty, staged, untracked, branch, and
worktree state until the consumer's Git safety owner classifies it. Keep
product behavior, environment policy, tests, CI, credentials, and runtime
semantics with their consumer owners.

This common base only establishes the consumer instruction boundary. It does
not re-own task procedures, command recipes, role lifecycles, implementation
policy, validation schemas, or AgentCanon source-editing policy. Those details
belong to the consumer-specific section or the consumer's own canonical owner.

Before selecting or editing a consumer surface, establish the actual working
directory and Git root, branch, and `HEAD`, then trace the selected owner's
dependency and consumer edges. Inspect the actual `HEAD` of every in-scope
dependency checkout and its pin when present; a named path is only a candidate
until that trace confirms the responsible replaceable unit. Record no dependency
only after the trace shows that no edge applies, never from an unperformed
inspection. Re-read this identity and dependency state after a directory,
branch, dependency checkout, or pin change; unchanged ordinary commands do not
require duplicate readback.

## Runtime Owner Map

| Responsibility | Consumer canonical owner | Validation / reader route |
| --- | --- | --- |
| product implementation and behavior | consumer source and design owners | consumer implementation route |
| build, tests, and runtime environment | consumer build and test owners | consumer execution route |
| repository structure and file placement | consumer structure owner | consumer structure route |
| root instruction extension | consumer-specific section in this file | consumer instruction route |
| AgentCanon source maintenance | selected AgentCanon development checkout | AgentCanon maintenance route |

## Task Entry

Start with this common base and the appended consumer-specific instructions.
Resolve the task owner and the consumer validation oracle from those surfaces.
When the task changes AgentCanon itself, move to a qualified AgentCanon
development checkout and keep the consumer tree unchanged unless the consumer
task explicitly owns the resulting generated file.

When a root `AGENTS.md` begins with the literal `@ROOT_AGENTS.md`, read this
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

## Validation Routing

Use the validation route owned by the changed consumer responsibility. Validate
the changed contract and its failure semantics, then use the consumer's normal
closeout route when required. A generated root file does not authorize
unrelated AgentCanon checks, product checks, or runtime changes.
