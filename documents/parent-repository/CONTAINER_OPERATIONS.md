<!--
@dependency-start
contract reference
responsibility Retired parent container projection documentation redirect.
upstream design ../runtime/bootstrap-runtime.md current shared runtime boundary
upstream implementation ../../bootstrap.sh current host lifecycle entrypoint
@dependency-end
-->

# Retired: parent container operations

The former document coupled parent containers to AgentCanon's vendored source
and `.devcontainer` lifecycle. It is no longer an active contract.

Use [Standalone Bootstrap And Shared Tool Runtime](../runtime/bootstrap-runtime.md)
for AgentCanon's one shared non-root Python/Rust/LSP tool container. Use the
parent repository's own Dockerfile, test runner, and GPU wrapper for product
execution. Do not restore a vendor checkout, submodule, root projection, or
AgentCanon `.devcontainer` to make either plane work.
