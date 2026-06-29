<!--
@dependency-start
contract reference
responsibility Documents the canonical full-expansion C++ template source to Lean evidence route.
upstream implementation ../../tools/agent_tools/cpp_template_to_lean.py expands C++ source roots into Lean.
upstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts the C++ source envelope.
upstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders complete operational IR.
downstream implementation ../../tests/agent_tools/test_cpp_template_to_lean.py validates the single CLI route.
downstream design ../tools/README.md lists proof and algorithm tool routes.
@dependency-end
-->

# cpp_template_to_lean.py

`tools/agent_tools/cpp_template_to_lean.py` is the canonical C++ template
algorithm to Lean evidence route. It takes one C++ source root, fully expands
the reachable parsed source implementation into the shared thin operational IR,
enumerates static branch / loop / switch path classes, checks complete
coverage, and writes Lean evidence definitions in one command.

The lower-level `cpp_source_canonical_ir.py` and `operational_ir_to_lean.py`
tools remain implementation components and diagnostic helpers. Formal proof
workflows should call this tool for C++ template source roots instead of
manually chaining the lower-level tools.

## Reader Map

- Owns the canonical full-expansion C++ template source to Lean evidence route.
- Main path: Command, Expansion And Coverage Contract, Output Contract, and
  Boundary.
- Read this before generating Lean evidence from C++ template source roots.
- Boundary: lower-level C++ IR and operational IR tools are diagnostic
  components, not the preferred formal-proof entrypoint for this route.

## Command

```bash
python3 tools/agent_tools/cpp_template_to_lean.py \
  --root . \
  --cpp-symbol include/algorithm.hpp::solve \
  --namespace Generated.CppSolve \
  --module-name SolveOperationalIr \
  --out lean/cpp_solve/Generated/SolveOperationalIr.lean \
  --record-out reports/cpp-source-ir/solve.json
```

`--cpp-symbol` uses `path.cpp::qualname` syntax. C++ `::` separators are
normalized to dotted source symbols in the generated record, so
`include/algorithm.hpp::Stepper::step` becomes `Stepper.step`.

When `--out` is omitted, generated Lean text is written to stdout. When
`--record-out` is supplied, the fully expanded C++ source-canonical JSON record
is also written. That JSON artifact is useful for repair and theorem-graph
projection, but the accepted C++ to Lean route is still this single command.

## Expansion And Coverage Contract

The command performs the route as one tool operation:

1. Resolve the selected C++ root from `--cpp-symbol`.
2. Build an `agent-canon.cpp-source-canonical-ir.v1` source envelope.
3. Fully expand reachable parsed calls into `agent-canon.thin-operational-ir.v2`.
4. Enumerate `code_paths` for every reachable parsed function.
5. Reject incomplete operational or code-path coverage before writing Lean.
6. Render Lean evidence definitions from the complete expanded record.

Coverage is complete only when:

- `coverage.unresolved_call_targets` is present and empty;
- `coverage.unassigned_op_count` is present and zero;
- `coverage.unmapped_code_path_functions` is present and empty;
- `coverage.code_path_count` covers all reachable parsed functions;
- all required structural counters needed by the renderer are present.

If coverage is incomplete, the command fails with `incomplete operational
coverage` and writes no Lean output. A requested `--record-out` can still be
written so the missing expansion target is visible to the extractor repair
loop.

## Output Contract

The generated Lean module contains evidence definitions for:

- input schema and selected provenance fields;
- public-interface metadata;
- source facts;
- allowed operation kinds and function signatures;
- operational functions, regions, operations, and expansion edges;
- static code-path rows and code-path decisions;
- structural coverage counters;
- empty `unresolvedCallTargets`;
- empty `unmappedCodePathFunctions`;
- `codePathCoverageComplete`;
- `coverageComplete`, a Boolean coverage fact.

The optional JSON record contains the same C++ source envelope documented by
`cpp_source_canonical_ir.py`.

## Boundary

This tool does not prove C++ correctness, floating-point semantics, progress,
termination, residual quality, certificate soundness, or backend lowering
correctness. It also does not dynamically unroll loops. Loop evidence is a
complete static path-class summary: zero-iteration and one-or-more-iteration
classes for `while` / `for`, plus condition and source-line evidence. It only
provides complete implementation-shape evidence for the selected source route.
Theorem targets, assumptions, bridge lemmas, and checker-backed proof status
remain owned by `$formal-proof-workflow` and the project proof theme.
