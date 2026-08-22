<!--
@dependency-start
contract design
responsibility Retired parent dependency-manifest design redirect.
upstream design ../../runtime/bootstrap-runtime.md current shared runtime contract
@dependency-end
-->

# Retired: parent dependency manifest follow-up

The former parent/vendor dependency-manifest design is retired. It described
an AgentCanon `.devcontainer` and parent lookup of a vendored dependency
manifest; neither is part of the current source-free parent contract.

Use [Standalone Bootstrap And Shared Tool Runtime](../../runtime/bootstrap-runtime.md)
for AgentCanon Python/Rust/LSP dependencies. Parent-specific dependencies remain
owned by the parent's Dockerfile or test environment.
