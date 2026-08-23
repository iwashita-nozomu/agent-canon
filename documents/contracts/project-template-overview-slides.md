<!--
@dependency-start
contract reference
responsibility Redirects the retired template/submodule overview to current standalone integration documentation.
upstream design ../runtime/bootstrap-runtime.md current AgentCanon tool-runtime boundary
upstream design ./derived-repo-bootstrap-runbook.md source-free parent onboarding
@dependency-end
-->

# Retired: project-template overview slides

The former slide deck described `project_template` as a submodule consumer and
included AgentCanon `.devcontainer`, root-view, and credential-forwarding
details. Those are historical and are not current operating instructions.

Use the [derived repository bootstrap runbook](derived-repo-bootstrap-runbook.md)
for a source-free parent and [Standalone Bootstrap And Shared Tool Runtime](../runtime/bootstrap-runtime.md)
for AgentCanon's shared Python/Rust/LSP tool container. Parent Docker, tests,
GitHub Actions, and GPU execution remain owned by the parent project.
