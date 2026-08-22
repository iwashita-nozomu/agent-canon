# Retired AgentCanon projection queue workflow

<!--
@dependency-start
contract workflow
responsibility Redirects the retired parent projection queue to the standalone source PR and bootstrap cleanup owners.
upstream design agent-canon-pr-workflow.md standalone source PR workflow
upstream design ../../documents/runtime/bootstrap-runtime.md runtime cleanup contract
@dependency-end
-->

The former workflow coordinated a downstream AgentCanon submodule pin, root
projections, and parent PR queue. That topology is retired. A parent must not
enqueue or consume AgentCanon projection work.

Use [AgentCanon Source PR Workflow](agent-canon-pr-workflow.md) for source
branch, review, merge, and merged-main readback. Use [Standalone Bootstrap And
Shared Tool Runtime](../../documents/runtime/bootstrap-runtime.md) for the one
shared tool container, external runtime spool, eval archive handoff, and
task-owned cleanup. Parent product validation and parent PRs remain separate
runnable units.
