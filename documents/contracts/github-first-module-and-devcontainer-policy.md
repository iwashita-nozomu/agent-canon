<!--
@dependency-start
contract reference
responsibility Retired parent module and Dev Container policy redirect.
upstream design ../runtime/bootstrap-runtime.md current standalone runtime boundary
upstream implementation ../../bootstrap.sh current host lifecycle entrypoint
@dependency-end
-->

# Retired: parent module and Dev Container policy

This document no longer defines an active integration route. The former
contract required a parent `vendor/agent-canon` submodule, root projections, and
an AgentCanon-owned `.devcontainer`; those surfaces are retired and must not be
reintroduced.

For current behavior, read:

- [Standalone Bootstrap And Shared Tool Runtime](../runtime/bootstrap-runtime.md)
  for the one shared Python/Rust/LSP tool container and external runtime root.
- [AgentCanon Update](../../agents/skills/agent-canon-update.md) for source
  changes and the qualified ignored parent development clone.
- [Derived repository bootstrap runbook](derived-repo-bootstrap-runbook.md) for
  the source-free parent movement and ownership boundary.

A parent keeps its own product Docker/test entrypoint when it needs one. It
does not initialize an AgentCanon module, mount AgentCanon tests, or use a
parent `.devcontainer` as an AgentCanon tool-runtime fallback.
