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
and DevContainer Setup first, then Runtime Boundary, Canonical Layout, Migration
Order, and Sequential Migration Policy before changing tool implementations.
The remaining sections list completed migrations, first targets, Python-only
surfaces, audit and plan commands, MCP surfaces, deterministic search, and validation.

## Goals

- Move heavy static-analysis and inventory tooling from Python to Rust.
- Keep workflow orchestration and rapidly-changing agent logic in Python.
- Declare the exact Rust toolchain and cargo source build in the mounted
  DevContainer dependency manifest.
- Keep template and derived Dockerfiles Rust-free unless the project runtime itself requires Rust.

## DevContainer Setup

Rust toolchains belong in the `rust-toolchain` record of
`.devcontainer/dependencies.toml`; the shared post-create only orchestrates the
validated plan and lifecycle projections.

Required components:

- rustup
- cargo
- rustfmt
- clippy
- rust-analyzer

The shared DevContainer installs Rust, publishes the Rust toolchain on the
container PATH for non-interactive `devcontainer exec` commands, and builds the
canonical AgentCanon CLI into:

```text
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/agent-canon/bin/agent-canon
```

with `/usr/local/bin/agent-canon` as a compatibility symlink. Older containers
may still have `/opt/agent-canon/bin/agent-canon`; new post-create runs use
`~/.tools` for compiled agent-tool binaries.

The `cargo-source-build` record selects `source_identity = "active-source"` and
always invokes `cargo build --release --locked`. Cargo owns incremental/change
detection for the mounted source tree, and the build input remains independent
of repository metadata. The published `.build-state` records only
`agent_canon_source_root`; active-source installation publishes no commit
provenance or source-identity receipt.
Records that select an explicit `commit` retain their existing Git commit
verification and provenance checks.

Repository search uses the deterministic Python `search.py` / `search_index.py`
surfaces and the Rust `semantic-index` command. No model server, installer,
model cache, or compatibility dispatch is part of the compiled-tool cache.

After the AgentCanon CLI is built, DevContainer post-create also runs
`agent-canon structured-analysis build --root <workspace> --profile devcontainer`
as a warning-only cache rebuild. This rebuild creates the SQLite intermediate
representation under
`${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}`
then materializes warning rows in a separate `diagnostics.sqlite` DB. It does
not rewrite repository source files or generated README surfaces.

In a template or derived repository, the normal adoption path is:

1. Create or reuse an ignored qualified AgentCanon source clone and an
   Issue-qualified standalone topic branch.
1. Run `bootstrap.sh install` with an explicit control/runtime root. The image
   build compiles and verifies the Rust CLI from the selected source snapshot;
   no Host Rust toolchain or separate rebuild script is used.
1. Use `agent-canon rust-migration-audit --root <agent-canon-source>` to confirm
   the Rust foundation is present.
1. Use `agent-canon rust-migration-plan --root <agent-canon-source>` before
   porting the next tool.

The parent repository does not need Rust in its project Dockerfile to use
AgentCanon Rust tooling. The shared tool image and the project execution image
remain separate contracts.

## Runtime Boundary

Rust compiler toolchains must not be installed through:

- `docker/Dockerfile`
- runtime images
- template root Docker build contracts

Rust is a development/runtime ergonomics surface owned by `.devcontainer/`.

## Canonical Layout

```text
rust/
  agent-canon/
    Cargo.toml
    src/

tools/
  bin/
    agent-canon
```

`tools/bin/agent-canon` is the stable runtime entrypoint.

## Migration Order

1. DevContainer Rust toolchain setup.
1. Rust CLI smoke tests.
1. Rust migration inventory and migration-leak checker.
1. Port inventory/static-analysis tools.
1. Keep workflow/orchestration tools in Python until stable.

## Sequential Migration Policy

Repos that vendor AgentCanon should not invent their own Rust migration order.
After updating the AgentCanon pin, run:

```bash
agent-canon rust-migration-plan --root vendor/agent-canon --limit 12
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

- vector_search.py
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

In a template or derived repository, the AgentCanon source root is the submodule:

```bash
agent-canon rust-migration-audit --root vendor/agent-canon
```

The audit checks:

- the Rust migration document, crate manifest, CLI entrypoint, audit module,
  and stable wrapper exist;
- `.devcontainer/dependencies.toml` declares the Rust toolchain, developer
  components, and locked cargo source build; post-create publishes the resulting
  `~/.tools` release CLI cache and `/usr/local/bin/agent-canon` entrypoint;
- `docker/Dockerfile` does not install rustup or run cargo as an agent-tooling
  convenience path.

## Rust Migration Plan

The planning command is read-only:

```bash
agent-canon rust-migration-plan --root .
```

In a template or derived repository:

```bash
agent-canon rust-migration-plan --root vendor/agent-canon
```

It reports:

- whether the DevContainer and CLI foundation is present;
- how many hook log files were inspected;
- ranked `RUST_MIGRATION_CANDIDATE` lines;
- `RUST_MIGRATION_KEEP_PYTHON` boundaries that should not be ported just
  because a tool was recently used.

## MCP Preflight Rust Tools

## Deterministic Search Surfaces

Purpose-based repository search remains an explicit deterministic tool surface:

```bash
python3 tools/analysis/search/search_index.py build --root .
python3 tools/analysis/search/search.py \
  --purpose "find responsibility scope tooling" \
  --providers text,semantic,vector,tool,header-deps,code-deps \
  --format json
```

The Rust `semantic-index` command owns SQLite-backed vector evidence. The
Python coordinator combines deterministic cards, exact text, TF-IDF, tool
catalog, dependency-header, and Python call facts. Neither surface is edit or
review authority; ownership and dependency evidence remain separate gates.

## Validation

```bash
cargo fmt --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml -- --check
cargo clippy --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml
agent-canon rust-migration-audit --root .
agent-canon rust-migration-plan --root .
python3 tools/analysis/search/search.py --help
python3 tools/analysis/search/search_index.py --help
python3 tools/runtime/manifest/tool_catalog.py
python3 tools/validation/semantic/tools/tool_drift.py
python3 tools/ci/container_config.py
```
