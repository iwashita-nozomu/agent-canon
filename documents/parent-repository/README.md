<!--
@dependency-start
contract reference
responsibility Retired parent integration documentation redirect.
upstream design ../runtime/bootstrap-runtime.md current shared runtime boundary
upstream implementation ../../bootstrap.sh current host lifecycle entrypoint
@dependency-end
-->

# Retired: parent repository integration guide

The former parent guide described a tracked AgentCanon submodule, root
symlinks, and a parent-owned projection surface. That integration is retired.

For current parent usage, read:

- [Derived repository bootstrap runbook](../contracts/derived-repo-bootstrap-runbook.md)
  for source-free parent onboarding.
- [Standalone Bootstrap And Shared Tool Runtime](../runtime/bootstrap-runtime.md)
  for the shared Python/Rust/LSP runtime.
- [AgentCanon Update](../../agents/skills/agent-canon-update.md) for a qualified
  ignored `workspace/agent-canondevelop/<qualified-task>/agent-canon` source clone.

Parent product code, Docker, tests, CI, and GPU execution remain parent-owned.
The parent does not initialize or mount AgentCanon source, tests, or eval
directories.
