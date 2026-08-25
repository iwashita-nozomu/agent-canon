# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the common, source-free base for a consumer repository's generated root AGENTS.md.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and consumer composition boundary
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
downstream implementation tools/agent_tools/entrypoint_composer.py composes the regular consumer root file
downstream implementation tools/agent_tools/check_entrypoint_owner_map.py validates the base grammar
@dependency-end
-->

This is the common base for a consumer repository's root `AGENTS.md`. The
consumer keeps that generated file as a regular tracked file by composing this
base with its own specific instructions. The composition is an explicit
consumer maintenance operation; it is not a live AgentCanon projection,
runtime import, updater, vendor checkout, submodule, or symlink.

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

## Validation Routing

Use the validation route owned by the changed consumer responsibility. Validate
the changed contract and its failure semantics, then use the consumer's normal
closeout route when required. A generated root file does not authorize
unrelated AgentCanon checks, product checks, or runtime changes.
