<!--
@dependency-start
contract reference
responsibility Documents tools/agent_tools/operational_ir_to_lean.py usage and output contract.
upstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders Lean evidence definitions.
upstream design cpp_source_canonical_ir.md defines the C++ source envelope.
upstream design jit_canonical_ir.md defines the shared thin operational IR shape.
downstream implementation ../../tools/agent_tools/cpp_template_to_lean.py owns the canonical C++ template source route.
downstream implementation ../../tests/agent_tools/test_operational_ir_to_lean.py validates the renderer.
@dependency-end
-->

# operational_ir_to_lean.py

`tools/agent_tools/operational_ir_to_lean.py` renders shared
`agent-canon.thin-operational-ir.v2` records into dependency-free Lean evidence
definitions. It is the generic renderer for already-expanded operational
records. For C++ template source roots, use `cpp_template_to_lean.py`, which
runs source expansion, complete-coverage checking, and Lean rendering as one
canonical tool operation.

## Reader Map

- Owns the generic renderer from already-expanded thin operational IR records
  to Lean evidence definitions.
- Main path: Command, Output Contract, and Boundary.
- Read this when rendering an existing operational IR record into Lean.
- Boundary: C++ template source roots should use `cpp_template_to_lean.py`
  rather than manually chaining lower-level tools.

## Command

```bash
python3 tools/agent_tools/operational_ir_to_lean.py \
  --ir reports/cpp-source-ir/solve.json \
  --namespace Generated.CppSolve \
  --module-name SolveOperationalIr \
  --out lean/cpp_solve/Generated/SolveOperationalIr.lean
```

`--ir` may point to either:

- a direct `agent-canon.thin-operational-ir.v2` JSON record; or
- an envelope containing an `operational_ir` object, such as
  `agent-canon.cpp-source-canonical-ir.v1`.

This input mode is intended for diagnostics, non-C++ wrappers, and proof
artifacts that already own the expansion record. It is not the canonical C++ to
Lean user route.

When `--out` is omitted, Lean text is written to stdout. `--module-name` is
optional and defaults from root metadata when available.

Generation requires complete operational coverage. The renderer fails before
writing Lean when `coverage.unresolved_call_targets` is non-empty,
`coverage.unassigned_op_count` is nonzero,
`coverage.unmapped_code_path_functions` is non-empty, `coverage.code_path_count`
does not cover all reachable functions, or the required completeness fields are
absent.

## Output Contract

The generated Lean module contains evidence definitions for:

- input schema and selected provenance fields;
- public-interface metadata when the input envelope provides it;
- source facts when the input envelope provides them;
- allowed operation kinds and function signatures;
- operational functions, regions, operations, and expansion edges;
- static code-path rows and per-path control decisions;
- structural coverage counters;
- `unresolvedCallTargets`, which must be empty for generated output;
- `unmappedCodePathFunctions`, which must be empty for generated output;
- `codePathCoverageComplete`;
- `coverageComplete`, a Boolean coverage fact.

The renderer preserves non-standard operation and coverage fields as key-value
metadata. It does not interpret those metadata fields as semantics.

## Boundary

This tool does not prove C++ correctness, floating-point semantics, progress,
termination, residual quality, certificate soundness, or backend lowering
correctness. It only makes implementation-shape evidence available to Lean.

Proof themes consume this generated evidence as provenance, then choose
theorem targets through `$formal-proof-workflow`. The theorem surface should be
based on public-root projections and checker-backed obligations, not on a
claim that generated low-level operation rows are already semantically correct.

The existing `agent-canon jit-ir-to-lean` command remains the JIT/StableHLO
renderer. It emits StableHLO and backend-specific evidence that this generic
tool intentionally does not model.
