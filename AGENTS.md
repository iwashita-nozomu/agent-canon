@ROOT_AGENTS.md
# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Provides the AgentCanon source-editing scope and conditional owner route.
upstream design documents/design/entrypoint-owner-map.md reading boundary
upstream design ROOT_AGENTS.md portable common constraints
downstream design agents/canonical/SOURCE_ROUTING.md optional source owner index
@dependency-end
-->

## Repository Role

These instructions apply when editing the AgentCanon repository itself. The
leading `@ROOT_AGENTS.md` requests the common base; consumer composition uses
that base rather than this source-only entrypoint.

## Runtime Owner Map

| Responsibility | Canonical owner | Reader route |
| --- | --- | --- |
| unresolved source owner | [source map](agents/canonical/SOURCE_ROUTING.md) | selected row only |

When a selected Skill's adapter or command context is unresolved, use
[Skill Paths](agents/canonical/skills.md#skill-paths). For formatting AgentCanon
files, use [formatter settings](documents/design/formatting.md#ownership-and-purpose).
