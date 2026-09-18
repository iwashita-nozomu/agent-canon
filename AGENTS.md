@ROOT_AGENTS.md
# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Provides the minimal source entrypoint and conditional owner route.
upstream design documents/design/entrypoint-owner-map.md reading boundary
downstream design ROOT_AGENTS.md portable common constraints
downstream design agents/canonical/SOURCE_ROUTING.md optional source owner index
@dependency-end
-->

## Repository Role

This file applies to the AgentCanon source checkout, not generated consumer roots.

## Reader Map

Use the known task owner directly. Consult the optional map below only to resolve
an unknown owner or request modality; read its matching row, not the whole index.

## Always-On Boundary

Keep automatically loaded instructions minimal. Read only applicable detail
sections; links and dependency metadata never require recursive or full reading.

## Runtime Owner Map

| Responsibility | Canonical owner | Reader route |
| --- | --- | --- |
| unresolved source owner | [source map](agents/canonical/SOURCE_ROUTING.md) | selected row only |

## Task Entry

Read the common base once, then the selected owner. Reuse unchanged context;
local AGENTS add only subtree-specific constraints, not duplicated parent policy.

## Validation Routing

Use the changed owner's existing formatter and validation route, not every linked
check. Detailed procedures belong in optional files, not another auto-loaded AGENTS.
