<!--
@dependency-start
contract reference
responsibility Explains the standalone AgentCanon runtime-surface inventory and archive boundary.
upstream design ./bootstrap-runtime.md bootstrap lifecycle and resource policy
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/surface_manifest.rs validates native source classifications
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/skill_projection_registry.rs resolves native generated skill owners
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs consumes normalized classifications
@dependency-end
-->

# AgentCanon Runtime Surfaces

This document is an auxiliary reader guide for the standalone AgentCanon tool
and bootstrap runtime. It grants no parent-repository synchronization authority.
It does not define parent-repository links, copies, submodules, root
views, deletion targets, or synchronization commands. A normal project keeps
its own source tree and invokes the shared runtime through `bootstrap.sh`.

## Owned surfaces

The machine-readable inventory in
`documents/runtime/shared-runtime-surfaces.toml` classifies four source-owned
families:

- `bootstrap/`: lifecycle manifest and container definition;
- `tools/`: Python orchestration, analysis, validation, and runtime adapters;
- `eval/`: evaluation producers, checkers, definitions, and fixtures;
- `tools/runtime/dispatch/agent-canon/`: the standalone Rust CLI crate.

The `normalized-snapshot` command emits schema
`agent-canon.surface-manifest.v2`. Its required `generated_projections` field
is the catalog/materializer mapping for ignored
`.codex/personal/skills/<skill>/SKILL.md` views; graph consumers resolve those
paths to tracked owners without creating the ignored view.

The default producer identity is
`agent-canon.surface-manifest-producer.v3`. Its producer path and SHA-256 bind
the canonical executable running the command. Native snapshot loading stays
inside that process and requires no Python interpreter. The selected source
root and manifest remain bound into the identity; the manifest must be a
canonical regular file within that source root.

An installed native executable can live outside the source root. This exception
applies only to v3 and only when the producer path equals the current executable.
A different outside-root artifact cannot obtain that authority by claiming v3.

Explicit external Python producers retain
`agent-canon.surface-manifest-producer.v2`: the producer and manifest must remain
canonical regular files beneath the declared source root, their hashes must
match, and producer path and identity must be supplied together. Their existing
Python execution interface is retained. The native default does not fall back
to an external producer on failure.

Graph build and status preserve explicit producer replay and content-change
rejection. Query and context remain bound to the current root's native identity.
A graph built with an external v2 identity does not become a native v3 graph;
default status requires a rebuild when the identities differ. Missing or invalid
persisted identity evidence remains stale or rejected by the existing guards.
The normalized snapshot schema itself remains `agent-canon.surface-manifest.v2`.

The former owned Python surface-manifest entrypoint is retired. The Python
skill-projection library remains for the source-only Python dependency graph
and as an independent migration oracle; it is still counted as pending in the
all-owned-tools migration.

Evaluation results are collected into the external `agent-canon-log` repository.
Runtime state, caches, temporary files, and receipts stay below the explicit
external runtime root. The AgentCanon source checkout must not retain published
runtime logs or copied project artifacts.

## Boundary

The runtime container is a shared tool environment. Project code executes in
the project-owned environment and is passed to a selected tool through an
explicit target. The source inventory is read-only classification metadata;
it is not a synchronizer and cannot mutate a parent repository root.

`projection_forbidden_roots = ["rust"]` records that the legacy top-level Rust
projection is forbidden while the canonical crate at
`tools/runtime/dispatch/agent-canon/` remains owned by AgentCanon itself. It does not grant cleanup
or deletion authority over another repository's `rust/` directory.

## Validation

Use the bootstrap lifecycle described in [bootstrap-runtime.md](bootstrap-runtime.md), then run the
standalone source checks for the changed tool or runtime surface. Check the
inventory with:

```bash
agent-canon surface-manifest --root . --prefix . \
  --manifest documents/runtime/shared-runtime-surfaces.toml normalized-snapshot
```
