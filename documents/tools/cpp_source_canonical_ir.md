<!--
@dependency-start
contract reference
responsibility Documents the native cpp-source-canonical-ir command and output contract.
upstream design jit_canonical_ir.md defines the shared thin operational IR shape.
downstream implementation cpp_template_to_lean.md owns the canonical C++ to Lean route.
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/cpp_source_canonical_ir.rs extracts C++ source-canonical IR.
downstream implementation ../../tests/agent_tools/test_cpp_source_canonical_ir.py validates C++ source extraction.
@dependency-end
-->

# cpp-source-canonical-ir

`agent-canon cpp-source-canonical-ir` extracts a source-only C++ slice
and emits the same nested thin operational IR used by the JIT-canonical
frontend. It is the internal source envelope producer and diagnostic record
tool behind `cpp-template-to-lean`; it is not the canonical user-facing C++
to Lean route.

## Reader Map

- Owns the diagnostic C++ source-canonical IR extraction contract.
- Main path: Command, Output Contract, and Boundary.
- Read this when inspecting or debugging the C++ source envelope behind
  `cpp-template-to-lean`.
- Boundary: this is not the canonical user-facing C++ to Lean route; use
  `cpp-template-to-lean` for full expansion and Lean output.

## Command

```bash
tools/bin/agent-canon cpp-source-canonical-ir \
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
- `source_facts`: assignment and return equations extracted from the
  reachable parsed functions;
- `operational_ir`: an `agent-canon.thin-operational-ir.v2` record containing
  functions, regions, operations, expansion edges, code paths, and coverage
  counters.

The nested thin operational IR uses the generic operation kinds:

```text
Function, Let, Call, If, While, Case, Tuple, Projection, Primitive, Return
```

Function bodies are represented as regions. Resolved source calls add
`call_target` expansion edges to parsed target functions. Unresolved or external
calls remain visible as primitive call rows and are listed under
`coverage.unresolved_call_targets`; downstream Lean evidence generation rejects
records unless that list is empty and every operation is assigned to a region.

For every reachable parsed function, the tool emits at least one `code_paths`
row. Straight-line functions have one `straight_line` path. `if` contributes
`then` and `else` alternatives, `while` and `for` contribute `skip` and `enter`
alternatives, and `switch` contributes one alternative per shallow `case` /
`default` label when labels are visible. The tool enumerates the Cartesian
product of those static alternatives per function. This is a complete
source-shape path-class summary, not dynamic loop unrolling.

## Boundary

This tool deliberately does not emit `stablehlo`, `backend_trace`, backend
environment records, mathematical proof obligations, theorem slices, backend
assumptions, or Lean files. The previous C++ Algorithm Expansion IR prototype
was proof-oriented; this tool keeps only the source indexing and call-resolution
idea and joins the current operational IR surface.

For C++ template algorithm roots, use the single full-expansion route:

```bash
tools/bin/agent-canon cpp-template-to-lean \
  --root . \
  --cpp-symbol include/algorithm.hpp::solve \
  --namespace Generated.CppSolve \
  --module-name SolveOperationalIr \
  --out lean/cpp_solve/Generated/SolveOperationalIr.lean \
  --record-out reports/cpp-source-ir/solve.json
```

That command invokes the native extractor internally, checks complete operational and
code-path coverage, and renders Lean evidence only after the selected C++ source
route has no unresolved call targets, no unassigned operation rows, and no
reachable function missing a code-path row. It does not emit StableHLO/backend
evidence and does not claim semantic proof of the C++ algorithm.

The extraction contract prioritizes complete coverage for the selected source
route. If source parsing or call resolution leaves unresolved targets, the
record is a repair input for the extractor or selected C++ root, not an accepted
Lean evidence artifact.
