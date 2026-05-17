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

The shared DevContainer installs Rust and builds the canonical AgentCanon CLI into:

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

The first Rust command is:

```bash
agent-canon rust-migration-audit --root .
```

The audit checks:

- undocumented migrations
- duplicate migration targets
- missing Rust crates
- missing wrappers
- stale Python-only ownership
- migration inventory drift

## Validation

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
agent-canon rust-migration-audit --root .
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/tool_drift.py
python3 tools/ci/container_config.py
```
