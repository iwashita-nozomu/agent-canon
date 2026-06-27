<!--
@dependency-start
contract reference
responsibility Documents tools/agent_tools/jit_canonical_ir.py usage and output contract.
downstream implementation ../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived JIT-canonical IR and backend traces.
downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs consumes the generated JIT-canonical IR JSON.
@dependency-end
-->

# jit_canonical_ir.py

`tools/agent_tools/jit_canonical_ir.py` lowers a JIT-capable Python root and
writes machine evidence for proof themes. It is an AgentCanon tool. Topic-local
proof directories may call it, but they do not own the tool contract.

## Reader Map

- Owns the command, output contract, and boundary for JIT-canonical IR capture.
- Main path: Command, Output Contract, and Boundary.
- Read this before extracting StableHLO/JAX runtime traces into the thin
  operational IR shape.
- Boundary: this file documents capture and evidence shape; Lean rendering and
  C++ source routes are owned by their own tool docs.

## Command

```bash
export AGENT_CANON_JIT_JAX_PLATFORM=gpu
export AGENT_CANON_JIT_BACKEND_TARGET=cuda
export AGENT_CANON_JIT_IREE_CUDA_TARGET=sm_89

python3 tools/agent_tools/jit_canonical_ir.py \
  --python-symbol lean/<topic>/main.py::main \
  --input-factory lean/<topic>/main.py::example_inputs \
  --xla-dump-dir reports/<topic>/xla-dump \
  --out lean/<topic>/<root>_jit_canonical_ir.json \
  --stablehlo-out lean/<topic>/<root>.stablehlo.mlir \
  --backend-trace-dir lean/<topic>/backend-trace \
  --backend-trace-out lean/<topic>/<root>_backend_trace.json
```

Backend and runtime target selection is supplied through environment variables.
The tool reads `AGENT_CANON_JIT_JAX_PLATFORM`,
`AGENT_CANON_JIT_BACKEND_TARGET`, `AGENT_CANON_JIT_INPUT_DEVICE`,
`AGENT_CANON_JIT_CUDA_VISIBLE_DEVICES`, and
`AGENT_CANON_JIT_IREE_CUDA_TARGET` before importing JAX. When the JAX platform is
GPU/CUDA and no CUDA device env is already fixed, the tool probes `nvidia-smi`
for an available GPU slot and sets `CUDA_VISIBLE_DEVICES` for that child
process. When slot selection fails, it exits with `gpu_slot_blocker=...`; CPU
lowering is selected through an explicit JIT env profile.

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
  coverage status when lowering stops early;
- optional XLA CUDA compile evidence when `--xla-dump-dir` is supplied. The
  tool sets `XLA_FLAGS` before importing JAX, compiles the lowered root, and
  copies final `.ll`, `.bc`, `.ptx`, and assembly artifacts from the XLA dump
  into the backend trace directory.

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

The tool detects versioned `llvm-dis` executables such as `llvm-dis-15` as well
as an unversioned `llvm-dis`. `llvm-dis` is only needed when a backend emits
LLVM bitcode. CUDA XLA dumps usually provide `.ll` text directly; in that case
`llvm-dis` availability is still recorded in the backend environment but is not
the source of the captured LLVM text.

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
