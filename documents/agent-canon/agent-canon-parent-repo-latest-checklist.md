<!--
@dependency-start
contract reference
responsibility Defines parent readback after an AgentCanon source merge.
upstream design ./agent-canon-update-route.md standalone source update route
upstream design ../../documents/runtime/bootstrap-runtime.md explicit runtime lifecycle
@dependency-end
-->

# Parent AgentCanon readback checklist

This is a readback checklist, not a vendor or submodule update procedure.

- Qualify the source object as `iwashita-nozomu/agent-canon#<number>`.
- Fetch and record the merged AgentCanon `main` commit and tree.
- Keep the parent project source-free: no `vendor/agent-canon`, `.gitmodules`,
  root projection, source symlink, or copied AgentCanon policy.
- Run the parent-owned validation using its own Docker/test entrypoint.
- If AgentCanon tools are needed, use an explicit control parent and runtime
  root through `bootstrap.sh`; do not use source-local cache, reports, or evals.
- Record source, runtime, project-test, and archive evidence separately.
- Remove the exact task runtime and Docker resources after readback.
