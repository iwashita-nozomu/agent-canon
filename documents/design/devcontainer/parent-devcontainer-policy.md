<!--
@dependency-start
contract design
responsibility Retired parent Dev Container projection design redirect.
upstream design ../../runtime/bootstrap-runtime.md current shared runtime contract
@dependency-end
-->

# Retired: parent Dev Container policy

The former policy for projecting AgentCanon into a parent `.devcontainer` is
retired. AgentCanon no longer ships or discovers a `.devcontainer`, submodule,
or root projection.

Use [Standalone Bootstrap And Shared Tool Runtime](../../runtime/bootstrap-runtime.md)
for the shared non-root Python/Rust/LSP tool container. A parent may retain a
project-owned Dev Container for product work, but it is a separate execution
plane and must not be used as an AgentCanon runtime fallback.
