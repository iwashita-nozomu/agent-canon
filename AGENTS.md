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

This source-only entrypoint is not a consumer composition input. Its leading
`@ROOT_AGENTS.md` explicitly requests the common base once, not a native include.
Source owner routes replace consumer routes, never the shared constraints.

## Reader Map

Use the known task owner directly. Consult the optional map below only to resolve
an unknown owner or request modality; read its matching row, not the whole index.

When that responsibility is active, formatter settings and direct commands are
owned by [documents/design/formatting.md](documents/design/formatting.md).

## Always-On Boundary

Keep automatically loaded instructions minimal. Read only applicable detail
sections; links and dependency metadata never require recursive or full reading.

## Runtime Owner Map

| Responsibility | Canonical owner | Reader route |
| --- | --- | --- |
| unresolved source owner | [source map](agents/canonical/SOURCE_ROUTING.md) | selected row only |

## Task Entry

Read the selected owner after the common base. Reuse unchanged context;
shared constraints belong to ROOT and procedures to their selected owners.

## Validation Routing

Use the changed owner's existing formatter and validation route, not every linked
check. Detailed procedures belong in optional files, not another auto-loaded AGENTS.
