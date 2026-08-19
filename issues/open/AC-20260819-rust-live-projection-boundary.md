<!--
@dependency-start
contract issue
responsibility Tracks the exclusion of AgentCanon standalone Rust/Cargo source from live parent projection ownership.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md live Rust/parent artifact ownership boundary
downstream design ../../documents/runtime/shared-runtime-surfaces.toml machine-readable projection-forbidden root
downstream implementation ../../tools/agent_tools/surface_manifest.py fail-closed target/source/transition validation
downstream implementation ../../tools/sync_agent_canon.sh consumes only validated manifest renderers
downstream implementation ../../tests/agent_tools/test_rust_projection_boundary.py focused projection and cleanup regression
@dependency-end
-->

# live consumerのAgentCanon投影からRust surfaceを排除する

issue_id: AC-20260819-rust-live-projection-boundary
status: in_progress
source: user
severity: S2
problem: live AgentCanon manifestにRust pathは存在しないが、standalone Rust source、parent-owned legacy regular artifact、symlink/gitlink projectionを区別する機械可読な禁止境界がなく、将来のsurface登録またはcleanup ownershipでRust/Cargo責務がconsumerへ混入できる。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/805
done: live manifestがRust standalone rootをprojection-forbiddenとして宣言し、target/source/legacy/state/update-transitionの全registrationをfail closedにし、parent regular artifactをcleanup対象へせず、standalone Rust gateとlive parent標準routeを分離する。
affected_surfaces: documents/runtime/shared-runtime-surfaces.toml, documents/runtime/SHARED_RUNTIME_SURFACES.md, tools/agent_tools/surface_manifest.py, tests/agent_tools/test_rust_projection_boundary.py
edit_scope: owner-bounded
required_action: #796のexact five-surface projectionを維持したまま、Rust/Cargo sourceとparent Rust pathをactive projectionまたはAgentCanon-owned cleanupへ登録できない単一manifest policyを追加する。
close_condition: focused manifest/projection tests、document alignment、standalone/static repository checks、Issue mirror、PR required checksがpassし、parent artifact removalが別owner routeとして再現可能に記録される。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/805

## Baseline

- AgentCanon main: `0ea5bb6d5d0bfc2e027698612aeb6fc5a3c8b0c2`
- dependency branch: `agent/796-codex-projection-boundary@cfa20f3adbefa15ed627e686317dbad4eb93c52d`
- work branch: `fix/805-rust-projection-boundary`
- dependency PR: `iwashita-nozomu/agent-canon#799`
- consumer projection PR: `iwashita-nozomu/project_template#191`

## Confirmed state

The #796 branch narrows active live symlinks to exactly:

```text
AGENTS.md
.codex/config.toml
.codex/agents
.codex/hooks.json
.codex/hooks
```

AgentCanon source still correctly owns `rust/agent-canon/**` and the standalone
Rust static-gate unit. A historical consumer can independently contain a
regular path such as
`rust/agent-canon/tests/python_algorithm_contract_cli.rs`. A regular file is not
a projection edge, and the current bounded stale-symlink cleanup must not be
expanded to delete it.

The missing invariant is producer-side: no future surface, copy source,
repository state, legacy-removal entry, or update transition may claim the Rust
standalone root. Without that invariant, an apparently harmless manifest edit
can silently make Cargo/toolchain validation part of a live Python/JAX parent.

## Ownership model

Let `F` be paths equal to or below `rust`, `T` manifest-owned parent targets,
`S` materialized AgentCanon source paths, and `U` update-transition candidates.
The live manifest must satisfy:

```text
prefix_intersection(T ∪ S ∪ U, F) = ∅
```

`projection_forbidden_roots = ["rust"]` is intentionally separate from
`standalone_only` and `removed_legacy`. The former is a registration prohibition;
the latter modes participate in root-absence or stale-symlink cleanup. Mixing
them would incorrectly grant AgentCanon lifecycle ownership over parent regular
content.

## Path classification

- `vendor/agent-canon/rust/**`: AgentCanon standalone source/test owner.
- parent regular file or directory under `rust/**`: parent-owned content or
  historical artifact; no projection inference and no AgentCanon auto-delete.
- generated copy: regular parent bytes unless explicit parent provenance says
  otherwise; migration remains a parent issue/PR.
- symlink into `vendor/agent-canon/rust/**`: unmanaged projection edge; consumer
  structure check fails closed.
- gitlink/submodule below `rust/**`: explicit parent dependency edge, not a live
  root view; it requires a separate parent dependency contract.
- absent path: live-projection fixed point; no compatibility placeholder.

## Scope

- add one machine-readable Rust standalone exclusion to the existing live
  manifest;
- validate both manifest target and materialization source paths;
- reject Rust candidates in active, copy, regular, state, standalone-only,
  legacy-cleanup, and update-transition data;
- expose policy readback through the existing manifest CLI;
- keep the normalized `agent-canon.surface-manifest.v1` runtime snapshot
  unchanged so Rust graph consumers do not acquire a second schema;
- document parent regular/symlink/gitlink/generated-copy classification and a
  separate parent migration readback;
- prove `sync_agent_canon.sh` receives the same preflight through its existing
  single renderer authority;
- keep the standalone Rust gate in AgentCanon and out of live parent projection
  checks.

## Non-goals

- changing #796/#799's exact five live Codex surfaces;
- reimplementing #795's `tools/agent-canon` retirement;
- deleting or moving AgentCanon `rust/agent-canon/**` source/tests;
- adding Cargo or Rust tests to project_template or another consumer;
- deleting the historical jax_utils regular artifact in this repository;
- converting parent content into `removed_legacy`, `standalone_only`, or an
  update transition;
- redesigning GPU admission, runtime alignment, or standalone static-gate
  selection.

## Acceptance criteria

- [ ] `projection_forbidden_roots` identifies `rust` without adding a surface
  entry or normalized-snapshot field;
- [ ] target paths under/above `rust` fail before link/copy/state/cleanup specs
  render;
- [ ] aliases whose source lies under `rust` fail even when the parent target is
  elsewhere;
- [ ] update-transition candidates below `rust` fail closed;
- [ ] the exact five live symlink paths remain unchanged;
- [ ] root-absence and stale-symlink cleanup output contains no `rust` path;
- [ ] parent regular content remains present in the focused consumer fixture;
- [ ] regular, generated-copy, symlink, and gitlink/submodule classifications
  are documented with owner-specific handling;
- [ ] standalone Rust static gate remains AgentCanon-owned and live parent
  standard checks do not invoke it;
- [ ] focused tests, document check, repository static gates, Issue mirror, and
  PR checks pass;
- [ ] jax_utils artifact removal remains traceable as a separate parent change.
