# Native CPython provider

This Rust executable connects AgentCanon's external parser and trace operations
to CPython. The standalone AgentCanon CLI keeps its own build and
startup independent of Python. PyO3 owns interpreter attachment and Python
object lifetimes; the provider uses its safe API and forbids local unsafe code.

Build in the existing tool or consumer execution environment with
`PYO3_PYTHON` selecting its interpreter:

```sh
cargo build --locked --manifest-path tools/runtime/python-provider/Cargo.toml
```

The shared tool runtime installs it through the existing
[`compile.sh`](../container/compile.sh) route. Direct callers can install the
crate with `cargo install --locked --path tools/runtime/python-provider` and
place `agent-canon-python-provider` on `PATH`, or set
`AGENT_CANON_PYTHON_PROVIDER` to its executable path. Python's normal runtime
environment supplies optional packages such as `pypdf`.

The executable accepts `runtime`, `html-extract` with HTML bytes on stdin,
`pdf-extract` with PDF bytes on stdin, and
`trace-json <module-path> <symbol>`. Each operation writes one JSON result.
Provider exceptions return status `fail` and exit code 1; invalid CLI arguments
return exit code 2. The HTML operation uses the standard `HTMLParser` with
callbacks implemented in Rust. The PDF operation calls the installed `pypdf`; trace loading
executes the selected existing module through `runpy`. AgentCanon orchestration
stays in Rust.

The caller owns its provider environment and input/output filesystem authority.
Retire an old Python owner after its consumer and independent validation move to
this native route. JAX extraction retains its current owner until that move is
complete.
