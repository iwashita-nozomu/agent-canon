# Native CPython provider

This optional Rust executable connects AgentCanon to an explicitly selected
external CPython runtime. The standalone AgentCanon CLI keeps its own build and
startup independent of Python. PyO3 owns interpreter attachment and Python
object lifetimes; the provider uses its safe API and forbids local unsafe code.

Build in the existing tool or consumer execution environment with
`PYO3_PYTHON` selecting its interpreter:

```sh
cargo build --locked --manifest-path tools/runtime/python-provider/Cargo.toml
```

The executable accepts `runtime`, `pdf-extract` with PDF bytes on stdin, and
`trace-json <module-path> <symbol>`. Each operation writes one JSON result.
Provider exceptions return status `fail` and exit code 1; invalid CLI arguments
return exit code 2. The PDF operation calls the installed `pypdf`; trace loading
executes the selected existing module through `runpy`. AgentCanon orchestration
stays in Rust.

The caller owns its provider environment and input/output filesystem authority.
Retire an old Python owner after its consumer and independent validation move to
this native route. JAX extraction retains its current owner until that move is
complete.
