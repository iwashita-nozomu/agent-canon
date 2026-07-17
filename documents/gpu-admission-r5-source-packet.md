# AgentCanon GPU admission R5 source-packet identity

<!--
@dependency-start
contract design
responsibility Records the fixed GPU admission R5 source-packet identity and implementation boundary.
upstream design ./experiment_runner.md generic ExperimentRunner ownership boundary
upstream design ./runtime-profiles-and-check-matrix.md validation failure taxonomy and repair route
@dependency-end
-->

The authoritative packet is the read-only file
`/mnt/l/workspace/agent-canon-devcontainer-runtime-boundary/reports/agents/w1-tool-env-routing-20260716/candidate_universe_contract_amendment_r5.md`
with SHA-256
`23294f2606214157ed04e822128e29ece07ffd9f52223962199c87d3c0ce8d0d`.
The detailed design review `detailed_design_review_r5_u18.md` and document flow
review `document_flow_review_r5_u18.md` are both `APPROVE`.

The implementation owner is exact U-18 design-to-implementation/source
authority. The responsibility graph is checked by invariant, state transition,
owner, independent change reason, and observable effect; line count and file
length are not split criteria. A type co-locates operations only when shared
atomic consistency requires one owner transition. The graph explicitly rejects
Context/Adapter/Store/Owner absorption of discovery, reservation, freeze,
environment materialization, launch, completion, or cleanup.

The composition root orders source freeze, runtime identity, strict NVIDIA
inventory, process occupancy, atomic UUID reservation, immutable plan,
environment materialization, fixed ff97 generic runner, lifecycle capture,
reverse release, terminal outcome, exactly-once coverage, and PostToolUse
projection. Each owner invariant has one canonical production gate and one
targeted oracle; broad CI/test is regression or packaging evidence only.

The R5 route has no CPU, integer-index, UUID-prefix, direct-launch, or
compatibility fallback.
