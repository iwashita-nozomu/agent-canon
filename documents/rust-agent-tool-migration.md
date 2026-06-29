<!--
@dependency-start
contract reference
responsibility Documents Rust migration policy for AgentCanon tools.
upstream design README.md AgentCanon documentation index
upstream design ../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream environment ../.devcontainer/post-create.sh installs Rust toolchain and CLI
downstream implementation ../rust/agent-canon/src/main.rs Rust CLI entrypoint
downstream implementation ../rust/agent-canon/src/migration_audit.rs validates migration boundaries
downstream implementation ../rust/agent-canon/src/rust_migration_plan.rs prints sequential migration candidates
downstream implementation ../rust/agent-canon/src/structured_analysis.rs implements structured document inventory migration target
downstream implementation ../tools/bin/agent-canon stable shell wrapper
@dependency-end
-->

# Rust Agent Tool Migration

## Reader Map

Use this policy to answer which AgentCanon tools should move to Rust, which
logic should remain in Python, and how the migration is validated. Read Goals
and DevContainer Setup first, then Runtime Boundary, Canonical Layout, Migration
Order, and Sequential Migration Policy before changing tool implementations.
The remaining sections list completed migrations, first targets, Python-only
surfaces, audit and plan commands, MCP/local-LLM Rust surfaces, and validation.

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
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/agent-canon/bin/agent-canon
```

with `/usr/local/bin/agent-canon` as a compatibility symlink. Older containers
may still have `/opt/agent-canon/bin/agent-canon`; new post-create runs use
`~/.tools` for compiled agent-tool binaries.

llama.cpp follows the same compiled-tool cache rule:

```text
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/bin/llama-cli
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/bin/llama-server
```

The default local LLM model selector is
`ggml-org/SmolLM3-3B-GGUF:Q4_K_M`, used only by
`agent-canon local-llm classify-responsibility` for single-file advisory
responsibility review. `tools/agent_tools/file_responsibility_llm.py` is a
Python compatibility helper for eval and index internals, not the primary
operator entrypoint. Post-create fetches and builds llama.cpp through
`tools/install_llama_cpp.sh`; AgentCanon update/rebuild paths reuse the same
installer and rebuild an existing local llama.cpp checkout after pin updates.

After the AgentCanon CLI is built, DevContainer post-create also runs
`agent-canon structured-analysis build --root <workspace> --profile devcontainer`
as a warning-only cache rebuild. This rebuild creates the SQLite intermediate
representation under
`${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}`
then materializes warning rows in a separate `diagnostics.sqlite` DB. It does
not rewrite repository source files or generated README surfaces.

In a template or derived repository, the normal adoption path is:

1. Update the `vendor/agent-canon` submodule pin to an AgentCanon commit that
   contains this policy and the Rust CLI.
1. Repair shared root views with `bash tools/sync_agent_canon.sh link-root` if
   the root view drifts.
1. Run `make agent-canon-ensure-latest` or
   `bash tools/update_agent_canon.sh apply`; this calls
   `tools/rebuild_agent_tools.sh` after the AgentCanon pin is updated. If the
   host has no Rust toolchain, rerun the same target inside the DevContainer or
   recreate the DevContainer so `.devcontainer/post-create.sh` runs again.
   If llama.cpp was already installed under
   `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/src/llama.cpp`, the same rebuild
   path also recompiles `llama-cli` and `llama-server`.
1. Use `agent-canon rust-migration-audit --root vendor/agent-canon` to confirm
   the Rust foundation is present.
1. Use `agent-canon rust-migration-plan --root vendor/agent-canon` before
   porting the next tool.

The parent repository does not need Rust in its repo-local Dockerfile to use
AgentCanon Rust tooling. The DevContainer is AgentCanon-owned shared
development infrastructure; the Dockerfile remains a repo-local runtime and
dependency contract.

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
- tools/oop/python/readability.py
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
  components, `~/.tools` release CLI cache, and `/usr/local/bin/agent-canon`
  entrypoint;
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

## Local LLM Rust CLI

Local LLM responsibility review is now a Rust CLI command:

```bash
agent-canon local-llm classify-responsibility --print-prompt rust/agent-canon/src/local_llm.rs
```

The command owns the single-file responsibility prompt boundary and emits
`FILE_RESP_LLM_*` machine-readable fields. Search, index, and eval subcommands
are routed through the same CLI surface while their current Python engines
remain the compatibility implementation:

```bash
agent-canon local-llm search --purpose "find responsibility scope tooling"
agent-canon local-llm build-index
agent-canon local-llm eval
```

Do not add a second local LLM public entrypoint for responsibility analysis.
Port the remaining Python engines only when their tests, catalog row, docs, and
log-surface inventory are updated in the same change.

## Validation

```bash
cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/agent-canon/Cargo.toml
agent-canon rust-migration-audit --root .
agent-canon rust-migration-plan --root .
agent-canon local-llm --help
agent-canon local-llm classify-responsibility --root . --print-prompt rust/agent-canon/src/local_llm.rs
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/tool_drift.py
python3 tools/ci/container_config.py
```
