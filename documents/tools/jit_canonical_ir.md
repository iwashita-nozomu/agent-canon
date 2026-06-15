<!--
@dependency-start
responsibility Documents tools/agent_tools/jit_canonical_ir.py usage and output contract.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived JIT-canonical IR and backend traces.
downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs consumes the generated JIT-canonical IR JSON.
@dependency-end
-->

# jit_canonical_ir.py

`tools/agent_tools/jit_canonical_ir.py` lowers a JIT-capable Python root and
writes machine evidence for proof themes. It is an AgentCanon tool. Topic-local
proof directories may call it, but they do not own the tool contract.

## Command

```bash
python3 tools/agent_tools/jit_canonical_ir.py \
  --python-symbol lean/<topic>/main.py::main \
  --input-factory lean/<topic>/main.py::example_inputs \
  --jax-platform gpu \
  --backend-target cuda \
  --out lean/<topic>/<root>_jit_canonical_ir.json \
  --stablehlo-out lean/<topic>/<root>.stablehlo.mlir \
  --backend-trace-out lean/<topic>/<root>_backend_trace.json
```

For a proof theme whose root is the lowered `main` StableHLO, omit
`--backend-trace-dir` / `--backend-trace-out` and pass both
`--no-source-root` and `--no-backend-trace`. The output keeps the Python symbol
as metadata and emits StableHLO-rooted operational records.

## Output Contract

The tool writes:

- StableHLO text for the lowered root;
- `agent-canon.jit-canonical-ir.v1` JSON containing
  `agent-canon.thin-operational-ir.v2`;
- a thin operational IR with op kind, opcode, source line, text hash, tensor
  types, dtypes, function name, region id, parent operation id, and call target;
- StableHLO function records, function-body/control-flow region records, and
  expansion edges for function bodies, while regions, case branches, and call
  targets;
- coverage counters for op count, region count, expansion-edge count, maximum
  region depth, unresolved call targets, and unassigned operation rows.

When backend trace collection is enabled, the tool also writes:

- backend trace coverage, including compiler availability, phase traces,
  executable source dumps, LLVM IR summaries when available, and explicit
  coverage status when lowering stops early.

When `--no-source-root` is used, `source_root` is metadata-only and
`main_pattern` is `null`; downstream theorem graphs must use the HLO
operational program as the implementation root.

When `--no-backend-trace` is used, the JSON does not contain
`backend_environment` or `backend_trace`; downstream Lean generation must not
emit backend, IREE, or LLVM structures for that proof theme.

LLVM IR summaries are extracted from backend `.ll` artifacts. For each LLVM
module the trace records the artifact path, SHA-256 digest, module-level opcode
counts, module-level fast-math flag counts, and a per-function catalog with
signature, return/attribute text, parameter text, opcode counts, and fast-math
flag counts. It also records function-local basic blocks and instruction rows:
block label, source line, instruction ids, instruction result name, opcode,
operand text, full instruction text hash, fast-math flags, and whether the
opcode is a floating-point operation. Bitcode artifacts are also disassembled
through `llvm-dis` when available and then captured through the same LLVM text
path.

The thin operational IR uses these generic kinds:

```text
Function, Let, Call, If, While, Case, Tuple, Projection, Primitive, Return
```

The IR is recursive at the implementation-shape level: functions contain
regions, regions contain operation ids, and expansion edges connect control
operations and call sites to their generated regions or targets. It is still
thin: it does not assign mathematical roles such as KKT quality, residual
decrease, or convergence.

## Boundary

This tool does not generate mathematical proof obligations and does not decide
domain-specific correctness, residual or objective progress, certificate
soundness, or termination. Those claims belong to the theorem graph that
consumes the generated evidence.

StableHLO extraction is a compiler action. It is not a numerical experiment and
must not be treated as proof that the runtime result satisfies an optimization
specification.
