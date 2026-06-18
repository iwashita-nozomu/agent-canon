<!--
@dependency-start
responsibility Documents tools/agent_tools/cpp_source_canonical_ir.py usage and output contract.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py defines the shared thin operational IR shape.
downstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts C++ source-canonical IR.
downstream implementation ../../tests/agent_tools/test_cpp_source_canonical_ir.py validates C++ source extraction.
@dependency-end
-->

# cpp_source_canonical_ir.py

`tools/agent_tools/cpp_source_canonical_ir.py` extracts a source-only C++ slice
and emits the same nested thin operational IR used by the JIT-canonical Python
frontend. It is a source evidence helper for proof workflow design; it is not a
C++ compiler frontend and it does not generate Lean files.

## Command

```bash
python3 tools/agent_tools/cpp_source_canonical_ir.py \
  --root . \
  --cpp-symbol include/algorithm.hpp::solve \
  --format json \
  --out reports/cpp-source-ir/solve.json
```

`--cpp-symbol` uses `path.cpp::qualname` syntax. C++ `::` separators are
normalized to dotted source symbols in the emitted record, so
`include/algorithm.hpp::Stepper::step` becomes `Stepper.step`.

## Output Contract

The tool writes an `agent-canon.cpp-source-canonical-ir.v1` JSON record with:

- `root`: the requested C++ symbol, repo root, source path, and source kind;
- `source_root`: source path, root qualname, span, source hash, parameters,
  return type, and parser warnings;
- `public_interface`: source-level parameter and return-type metadata;
- `source_facts`: shallow assignment and return equations extracted from the
  reachable parsed functions;
- `operational_ir`: an `agent-canon.thin-operational-ir.v2` record containing
  functions, regions, operations, expansion edges, and coverage counters.

The nested thin operational IR uses the generic operation kinds:

```text
Function, Let, Call, If, While, Case, Tuple, Projection, Primitive, Return
```

Function bodies are represented as regions. Resolved source calls add
`call_target` expansion edges to parsed target functions. Unresolved or external
calls remain visible as primitive call rows and are listed under
`coverage.unresolved_call_targets`.

## Boundary

This tool deliberately does not emit `stablehlo`, `backend_trace`, backend
environment records, mathematical proof obligations, theorem slices, or backend
assumptions. The previous C++ Algorithm Expansion IR prototype was
proof-oriented; this tool keeps only the source indexing and call-resolution
idea and joins the current operational IR surface.

Current `tools/bin/agent-canon jit-ir-to-lean` consumes JIT-canonical records
with StableHLO and JAX public-interface coverage. For source-only C++ evidence,
use the generic renderer:

```bash
python3 tools/agent_tools/operational_ir_to_lean.py \
  --ir reports/cpp-source-ir/solve.json \
  --namespace Generated.CppSolve \
  --module-name SolveOperationalIr \
  --out lean/cpp_solve/Generated/SolveOperationalIr.lean
```

That command consumes the nested thin operational IR and preserves the C++
wrapper's provenance, public-interface metadata, source facts, and structural
coverage as Lean evidence data. It does not emit StableHLO/backend evidence and
does not claim semantic proof of the C++ algorithm.

The parser is lightweight. It handles common record declarations, namespaces,
function and method definitions, local constructor assignments, direct calls,
object method calls, brace construction, assignment facts, return facts, and
shallow `if` / `while` markers. It reports unresolved targets instead of
hiding parser limits.
