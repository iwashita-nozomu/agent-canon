<!--
@dependency-start
contract reference
responsibility Documents Rust migration policy for AgentCanon tools.
upstream design README.md AgentCanon documentation index
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream implementation ../../bootstrap/container/image/dependencies.toml declares Rust toolchain and CLI build records
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs Rust CLI entrypoint
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/migration_audit.rs validates migration boundaries
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/rust_migration_plan.rs prints sequential migration candidates
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/structured_analysis.rs implements structured document inventory migration target
downstream implementation ../../tools/bin/agent-canon stable shell wrapper
@dependency-end
-->

# Rust Agent Tool Migration

## Reader Map

Use this policy to answer which AgentCanon tools should move to Rust, which
logic should remain in Python, and how the migration is validated. Read Goals
and Shared Tool Image Setup first, then Runtime Boundary, Canonical Layout, Migration
Order, and Sequential Migration Policy before changing tool implementations.
The remaining sections list completed migrations, first targets, Python-only
surfaces, audit and plan commands, MCP surfaces, deterministic search, and validation.

## Goals

- Move heavy static-analysis and inventory tooling from Python to Rust.
- Keep workflow orchestration and rapidly-changing agent logic in Python.
- Declare the Rust toolchain in the shared tool image dependency manifest.
- Keep project images consumer-owned; provision Rust there when their product or development requirements call for it.

## Shared Tool Image Setup

AgentCanon's Rust toolchain belongs to the `rust-toolchain` record in
`bootstrap/container/image/dependencies.toml`. The shared tool image and
`bootstrap.sh` own installation; source-mounted Rust tools compile into the
resident runtime cache. Use the bootstrap-selected CLI and cache paths.

In a template or derived repository, use the selected qualified AgentCanon
source checkout and the shared bootstrap. Run `agent-canon rust-migration-audit`
and `agent-canon rust-migration-plan` against that source root before selecting
a tool migration. Project product/development images remain consumer-owned.

## Runtime Boundary

AgentCanon Rust tooling belongs in the shared AgentCanon tool image. Project
product or development images provide Rust when their own requirements call
for it; AgentCanon tooling uses the shared image.

## Canonical Layout

```text
tools/runtime/dispatch/
  agent-canon/
    Cargo.toml
    src/

tools/
  bin/
    agent-canon
```

`tools/bin/agent-canon` is the stable runtime entrypoint.

## Migration Order

1. Reuse the shared tool image and its Rust toolchain.
1. Rust CLI smoke tests.
1. Rust migration inventory and migration-leak checker.
1. Port inventory/static-analysis tools.
1. Keep workflow/orchestration tools in Python until stable.

## Sequential Migration Policy

Parent repositories should not invent their own Rust migration order. After
updating the qualified AgentCanon source clone, run:

```bash
agent-canon rust-migration-plan --root <agent-canon-source> --limit 12
```

Standalone AgentCanon checkouts use:

```bash
agent-canon rust-migration-plan --root . --limit 12
```

The plan combines this document's fixed first-target list with accumulated
hook and skill feedback logs from the mounted runtime log archive and legacy
`agents/evals/results/hook-runs/`. It emits
`port-now` entries for stable, repo-wide inventory or static-analysis tools,
`observe-before-port` entries for tools that appear in feedback logs but are
not yet stable migration targets, and `keep-python` entries for orchestration
tools that should stay Python-first.

Port one tool family at a time. A port is ready for review only when the Rust
tool preserves the old command's machine-readable output contract, the Python
entrypoint is either retired or kept as a caller-warning legacy migration shim,
and the tool catalog, docs, tests, and hook or workflow references point at the
current canonical command.

## Completed Rust Migrations

- Document-canon inventory has been absorbed into
  `agent-canon structured-analysis document-inventory`. The old Python
  entrypoint has been retired; callers use the Rust command directly.
- `agent-canon structured-analysis build` materializes the git-visible file
  tree as an `artifact` layer and imports document inventory findings into the
  `document-canon` layer of `prose_graph.sqlite`, then writes current warnings
  into `diagnostics.sqlite`.
- Tool-document responsibility checks have been absorbed into
  `agent-canon structured-analysis document-inventory` as generic
  `document_responsibility_gap` findings. The Rust checker derives these gaps
  from dependency-manifest responsibility and reusable coverage rules declared
  by upstream design documents. For example, any document that cites the Prose
  Reasoning Graph DSL as `upstream design` must cover the DSL spec's declared
  coverage groups, such as source-truth anchors, lower graph typed relations,
  derived projection views, and graph format records. It must not warn merely
  because a named heading or visual block is absent. No Python
  `prose_reasoning_graph.py` compatibility route emits those responsibility
  findings.

## First Rust Targets

Recommended first migrations:

- file_surface_inventory.py
- helper_function_inventory.py
- log_surface_inventory.py
- tools/validation/code/oop/python/readability.py
- dependency graph scanners

## Keep In Python

Keep these Python-first until behavior stabilizes:

- bootstrap_agent_run.py
- task_close.py
- evaluate_agent_run.py
- agent_canon_update_todos.py

## Rust Migration Audit

The first Rust command audits an AgentCanon source root:

```bash
agent-canon rust-migration-audit --root .
```

In a template or derived repository, `<agent-canon-source>` is the qualified
AgentCanon source root selected by the caller:

```bash
agent-canon rust-migration-audit --root <agent-canon-source>
```

The audit checks:

- the Rust migration document, crate manifest, CLI entrypoint, audit module,
  and stable wrapper exist;
- bootstrap entrypoints, the shared image manifest/Dockerfile, lifecycle,
  runtime-artifact and dispatcher owners are present with their required markers;
- `docker/Dockerfile` does not install rustup or run cargo as an agent-tooling
  convenience path.

## Rust Migration Plan

The planning command is read-only:

```bash
agent-canon rust-migration-plan --root .
```

In a template or derived repository:

```bash
agent-canon rust-migration-plan --root <agent-canon-source>
```

It reports:

- whether the shared bootstrap and CLI foundation is present;
- how many hook log files were inspected;
- ranked `RUST_MIGRATION_CANDIDATE` lines;
- `RUST_MIGRATION_KEEP_PYTHON` boundaries that should not be ported just
  because a tool was recently used.

## MCP Preflight Rust Tools

## Deterministic Search Surfaces

Repository search keeps `search.py` as a thin provider router: exact text and
catalog patterns use Git, dependency context uses the source graph owner, and
code facts use the LSP owner. Ranked semantic retrieval remains in the Rust
`semantic-index` command and its external cache; the Python route does not build
heuristic cards or combine provider scores. No model server, installer, model
cache, or compatibility dispatch is part of the compiled-tool cache.

The Python search entrypoint selects one or more native owners explicitly. Its
default `text` provider is stateless Git search; `--regex` and `--word-regexp`
use Git's own query syntax. Tool-catalog search is scoped to `tools/catalog.yaml`.
Dependency and code providers return source-graph and LSP results separately.

`semantic-index` owns ranked semantic/vector evidence and its cache. Selecting
that provider does not implicitly build or repair the cache. Provider outputs
remain separate and advisory; none is edit or review authority.

## Validation

```bash
cargo fmt --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml -- --check
cargo clippy --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml
agent-canon rust-migration-audit --root .
agent-canon rust-migration-plan --root .
python3 tools/analysis/search/search.py --help
python3 tools/runtime/manifest/tool_catalog.py
python3 tools/validation/semantic/tools/tool_drift.py
python3 tools/validation/ci/runners/container_runtime.py
```
