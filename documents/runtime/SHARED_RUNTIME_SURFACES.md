<!--
@dependency-start
contract reference
responsibility Explains the standalone AgentCanon runtime-surface inventory and archive boundary.
upstream design ./bootstrap-runtime.md bootstrap lifecycle and resource policy
upstream implementation ../../tools/agent_tools/surface_manifest.py validates source classifications
upstream implementation ../../tools/agent_tools/skill_projection_registry.py resolves generated skill owners
downstream implementation ../../rust/agent-canon/src/dependency_manifest.rs consumes normalized classifications
@dependency-end
-->

# AgentCanon Runtime Surfaces

This document is an auxiliary reader guide for the standalone AgentCanon tool
runtime. It does not define parent-repository links, copies, submodules, root
views, deletion targets, or synchronization commands. A normal project keeps
its own source tree and invokes the shared runtime through `bootstrap.sh`.

## Owned surfaces

The machine-readable inventory in
`documents/runtime/shared-runtime-surfaces.toml` classifies three source-owned
families:

- `bootstrap/`: lifecycle manifest and container definition;
- `tools/agent_tools/`: Python orchestration and tool adapters;
- `evidence/agent-evals/`: evaluation producers and collection metadata.

The `normalized-snapshot` command emits schema
`agent-canon.surface-manifest.v2`. Its required `generated_projections` field
is the catalog/materializer mapping for ignored
`.codex/personal/skills/<skill>/SKILL.md` views; graph consumers resolve those
paths to tracked owners without creating the ignored view.

The producer identity is
`agent-canon.surface-manifest-producer.v2`; consumers must reject older or
incomplete snapshots instead of silently treating them as equivalent.

Evaluation results are collected into the external `agent-canon-log` repository.
Runtime state, caches, temporary files, and receipts stay below the explicit
external runtime root. The AgentCanon source checkout must not retain published
runtime logs or copied project artifacts.

## Boundary

The runtime container is a shared tool environment. Project code executes in
the project-owned environment and is passed to a selected tool through an
explicit target. The source inventory is read-only classification metadata;
it is not a synchronizer and cannot mutate a parent repository root.

`projection_forbidden_roots = ["rust"]` records that the standalone Rust source
and Cargo target remain owned by AgentCanon itself. It does not grant cleanup
or deletion authority over another repository's `rust/` directory.

## Validation

Use the bootstrap lifecycle described in `bootstrap-runtime.md`, then run the
standalone source checks for the changed tool or runtime surface. Check the
inventory with:

```bash
python3 tools/agent_tools/surface_manifest.py --root . --prefix . \
  --manifest documents/runtime/shared-runtime-surfaces.toml normalized-snapshot
```
