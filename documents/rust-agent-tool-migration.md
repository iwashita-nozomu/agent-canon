<!--
@dependency-start
responsibility Documents Rust migration policy for AgentCanon tools.
upstream design README.md AgentCanon documentation index
upstream design ../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream environment ../.devcontainer/post-create.sh installs Rust toolchain and CLI
downstream implementation ../rust/agent-canon/src/main.rs Rust CLI entrypoint
downstream implementation ../rust/agent-canon/src/migration_audit.rs validates migration boundaries
downstream implementation ../tools/bin/agent-canon stable shell wrapper
@dependency-end
-->

# Rust Agent Tool Migration

## Goals

- Move heavy static-analysis and inventory tooling from Python to Rust.
- Keep workflow orchestration and rapidly-changing agent logic in Python.
- Install Rust only in DevContainer post-create flows.
- Keep template and derived Dockerfiles Rust-free unless the project runtime itself requires Rust.

## DevContainer Setup

Rust toolchains belong in `.devcontainer/post-create.sh`.

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
/opt/agent-canon/bin/agent-canon
```

with:

```text
/usr/local/bin/agent-canon
```

as a symlink.

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

## First Rust Targets

Recommended first migrations:

- vector_search.py
- file_surface_inventory.py
- noncanonical_document_inventory.py
- helper_function_inventory.py
- log_surface_inventory.py
- dependency graph scanners

## Keep In Python

Keep these Python-first until behavior stabilizes:

- bootstrap_agent_run.py
- task_start.py
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
- `.devcontainer/post-create.sh` installs the Rust toolchain, developer
  components, release CLI, and `/usr/local/bin/agent-canon` entrypoint;
- `docker/Dockerfile` does not install rustup or run cargo as an agent-tooling
  convenience path.

## Validation

```bash
cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/agent-canon/Cargo.toml
agent-canon rust-migration-audit --root .
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/tool_drift.py
python3 tools/ci/container_config.py
```
