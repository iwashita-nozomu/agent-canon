# AgentCanon GPU admission R5 source-packet identity

<!--
@dependency-start
contract design
responsibility Records the fixed GPU admission R5 source-packet identity and implementation boundary.
downstream design ../design/experiment_runner.md generic ExperimentRunner reader projection
upstream design ../runtime/runtime-profiles-and-check-matrix.md validation failure taxonomy and repair route
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

## Reviewer responsibility graph

The graph below is the source-review handoff. Each row is one cohesive owner,
not a line-count split. Operations that must share one atomic consistency
boundary remain together, especially candidate flock acquisition, fd-bound
readback, busy-candidate continuation, and total rollback in
`GpuReservationTransaction`.

| Owner | Invariant or state transition | Independent change reason and effect | Must not absorb | Canonical targeted gate |
| --- | --- | --- | --- | --- |
| `NvidiaInventoryProbe` | Exact driver/list/XML evidence becomes one complete physical/MIG topology. | NVIDIA grammar or topology changes; emits immutable opaque-UUID inventory. | Occupancy, locks, freeze, environment, launch | `test_nvidia_fixture_list_reject_*` and `test_nvidia_fixture_xml_reject_conflicting_join` |
| `GpuProcessOccupancyProbe` | A physical holder excludes all of its MIG children, and a MIG holder excludes its parent and leaf. Ambiguity fails closed. | PID, namespace, or process-visibility changes; emits occupied full UUIDs. | Discovery parsing, reservation, lifecycle | `test_gpu_process_occupancy_*` |
| `GpuReservationTransaction` | Each candidate is opened, flocked, reread, accepted, or rolled back as one transaction; a busy candidate alone continues. | Kernel, flock, tamper, or rollback behavior changes; emits one reservation receipt. | Discovery, source freeze, environment, launch | `test_gpu_reservation_*` |
| `SourceFreezeOwner` | Source membership, fd identity, bytes, snapshot, and exit revalidation are one fd-bound transition. | Source-layout or race policy changes; emits `SourceFreezeReceipt`. | GPU discovery/reservation, environment, lifecycle | `test_source_freeze_*` and `test_source_path_set_fails_closed_when_exact_registry_is_missing` |
| Runtime receipt functions and `RuntimeIdentityReader` | Exact root artifacts are atomically published, parsed once from no-follow fds, and joined only after namespace/UID/GID/groups/umask/bind identity matches. | Runtime namespace or receipt schema changes; emits `RuntimeIdentityReceipt`. | GPU policy, source freeze, launch, completion | `test_runtime_identity` |
| `build_admitted_environment` | The frozen selected full UUID set becomes the exact environment before runner construction. | Environment-key policy changes; emits immutable `AdmittedEnvironment`. | Discovery, reservation, launch, completion | `test_r5_admitted_environment_and_context_are_composition_only` |
| Frozen topic adapter (`_ManagedTopicCase`, bind, and task functions) | The selected canonical `experiments/<topic>/run.py` and argv execute only from snapshot bytes. | Topic entrypoint contract changes; emits one generic `ExecutionResult`. | Admission, source copying, environment policy, lifecycle serialization | `test_normal_cli_binds_frozen_topic_to_ff97_lifecycle` |
| ff97 `StandardRunner` and scheduler | Exactly one generic `run(worker)` call returns `None`; scheduler completions and lifecycle evidence remain generic-owner state. | Generic lifecycle changes; emits scheduler completion and typed lifecycle evidence. | Admission policy, terminal projection, GPU cleanup | `test_r5_runner_lifecycle_capture_is_finally_bound_for_interruptions` |
| `ManagedGpuOutcomeReducer` | Every terminal route normalizes once into one total outcome and complete fingerprint preimage. | Terminal taxonomy or fingerprint changes; emits `ManagedGpuOutcome`. | Completion persistence, Hook dispatch | `test_r5_terminal_coverage_projection_is_exact_and_hook_validated` |
| `CompletionCoverageAdapter` | Planned chunks and typed absences are persisted exactly once. | Completion schema or persistence changes; emits one coverage record. | Outcome classification, Hook validation | The same terminal-to-coverage chain gate above; no broad duplicate |
| `PostToolUseProjectionReducer` | The total outcome/coverage pair becomes the canonical projection bytes. | Projection schema changes; emits the nine-key projection. | Admission, lifecycle, Hook validation | The same terminal-to-projection chain gate above; dispatcher/guard tests validate transport only |
| `RunGpuAdmissionContext` | Composition order and reverse-total release are the only state it owns. | Collaborator wiring or release order changes; emits no semantic admission value. | Discovery, reservation, freeze, environment materialization, launch, completion semantics, cleanup policy | `test_r5_admitted_environment_and_context_are_composition_only` |
| Dispatcher and projection guard | Dispatcher normalizes and orders child input; the guard validates only the reducer-produced bytes. | Hook transport/schema validation changes; emits only validated child stdout. | Projection production, admission, launch, completion | `test_execution_resource_plan_projection_guard_dispatch` and `test_post_tool_projection_dispatch` |

`UUIDReservationStore` remains isolated from the managed R5 route. The
production NVIDIA probe receives no legacy store, and the legacy planner fails
typed instead of becoming a compatibility fallback. The frozen topic adapter
does not freeze source itself, and the runtime receipt reader does not publish
or repair identity state.

The composition root is therefore ordering-only:

```text
freeze -> identity -> discovery -> occupancy -> reservation -> plan
       -> environment -> one ff97 run -> outcome -> completion -> projection
       -> reverse release
```

`RunGpuAdmissionContext` may register collaborator release callbacks and record
its own one-shot composition state. It may not recompute a collaborator
invariant, retain a second semantic receipt, or choose a fallback. This is the
`composition-root-only` review condition.
