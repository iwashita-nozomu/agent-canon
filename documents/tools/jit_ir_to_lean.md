<!--
@dependency-start
responsibility Documents agent-canon jit-ir-to-lean usage and current Lean output boundary.
downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR JSON into Lean evidence definitions.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py produces the consumed JIT-canonical IR JSON.
@dependency-end
-->

# jit-ir-to-lean

`agent-canon jit-ir-to-lean` converts JIT-canonical IR JSON into a generated
Lean evidence module. It is an AgentCanon Rust CLI command.

## Command

```bash
tools/bin/agent-canon jit-ir-to-lean \
  --jit-ir lean/<topic>/<root>_jit_canonical_ir.json \
  --namespace <Lean.Namespace> \
  --module-name <root>_jit_canonical \
  --out lean/<topic>/<LeanNamespace>/Generated<Root>JitCanonical.lean
```

## Current Lean Output

The current implementation emits a generated operational-program evidence
module and a fuelled Lean operational evaluator:

- `OperationalOp`, one row per StableHLO/MLIR operation selected by the thin IR;
- `OperationalFunction`, one row per StableHLO function;
- `OperationalRegion`, one row per function body or control-flow region;
- `ExpansionEdge`, connecting functions, control operations, regions, and call
  targets;
- `OperationalProgram`, grouping the generated functions, regions, expansion
  edges, entry function, and operation counts;
- `OperationalCoverage`, retaining the extractor's structural coverage summary;
- `JitCanonicalFunction`, tying the root symbol, input factory, StableHLO hash,
  allowed op kinds, operation catalog, operational program, and coverage
  summary together;
- `OperationalRuntimeState`, `OperationalFrame`, and `OperationalValue`, the
  generated evaluator state used to compose function/region/op execution;
- `OperationalPrimitiveSemantics`, a parameter record for primitive numeric
  operation semantics and branch selection;
- `stepOperational`, a small-step function over generated frames and ops;
- `runOperationalFuel`, a fuelled evaluator for the generated operational
  program;
- `generatedMainInitialState`, `generatedMainFuel`, and
  `generatedMainSymbolicFuel`, tying the generated entry function to the
  fuelled evaluator;
- root, StableHLO-hash, lowering-coverage, unassigned-op, unresolved-call, and
  replay-trace theorems checked by Lean.
- for supported public `main(problem, InitializeConfig)` roots, source-return
  structures, `sourceMain`, source solve-config defaults, and
  `SourceMainExpansionCoverage`, which records whether source `initialize`,
  `algorithm.run`, and residual predicate semantics were value-expanded by the
  generator.

This output is enough to prove that a specific JIT root lowered to a specific
StableHLO evidence packet, that the generated operational program has no
unassigned operation rows or unresolved call targets, and that the generated
function/region/op graph is available as a Lean function parameterized by
primitive semantics.

If the input JSON omits `backend_trace`, the generated Lean module is HLO-only:
it does not emit backend, IREE, or LLVM structures and
`JitCanonicalFunction` has no backend field.

When the input JSON contains backend trace data, the generated module also
exposes:

```lean
def llvmModules : List LlvmModuleTrace
def llvmBasicBlocks : List LlvmBasicBlockTrace
def llvmInstructions : List LlvmInstructionTrace
def executeLlvmInstruction :
  LlvmPrimitiveSemantics ->
  LlvmRuntimeState ->
  LlvmInstructionTrace ->
  LlvmRuntimeState
def runLlvmInstructions :
  LlvmPrimitiveSemantics ->
  LlvmRuntimeState ->
  List LlvmInstructionTrace ->
  LlvmRuntimeState
def generatedLlvmRuntimeState : LlvmRuntimeState
theorem generated_backend_llvm_count_matches :
  generatedFunction.backend.llvmModuleCount = llvmModules.length
theorem generated_backend_llvm_basic_block_count_matches :
  llvmBasicBlocks.length = <generated count>
theorem generated_backend_llvm_instruction_count_matches :
  llvmInstructions.length = <generated count>
theorem generated_llvm_runtime_records_all_instructions :
  generatedLlvmRuntimeState.executedInstructionIds.length = llvmInstructions.length
```

Each LLVM module record contains the artifact path, SHA-256 digest, aggregate
opcode counts, aggregate fast-math flag counts, and per-function opcode /
fast-math summaries. Each function record references basic blocks and
instructions by label/id. The top-level block and instruction lists carry the
actual block rows and instruction rows. If backend lowering stops before LLVM,
these lists are `[]` and the coverage field records the last successful compiler
phase.
When the JIT-canonical IR contains XLA CUDA dump artifacts, the same generated
LLVM structures consume those `.ll` modules; after backend trace normalization,
the Lean output does not distinguish IREE-emitted LLVM from XLA-emitted LLVM.

`runLlvmInstructions` is intentionally parameterized by
`LlvmPrimitiveSemantics`. The default generated state uses a symbolic primitive
semantics that maps each instruction to its instruction-text hash. The theorem
graph can replace that primitive semantics with an LLVM/FP32/memory model
without changing the generated control-flow or instruction-order function.

## Boundary

The command does not currently emit:

- concrete semantics for `stablehlo.add`, `stablehlo.reduce`, tensor memory, or
  other numeric primitives;
- a concrete LLVM memory model or floating-point rounding model;
- theorem-specific claims such as progress, regularity, direction quality,
  certificate soundness, or termination.

Proof themes must cite the generated module as implementation provenance. The
generated `OperationalProgram` and `generatedMainFuel` are the Lean-side
reproduction of the JIT-lowered implementation shape and its fuelled
function/region/op composition. If backend trace data is present, the generated
LLVM runtime functions replay backend instruction rows as Lean functions.
Concrete numeric primitive semantics and theorem-specific mathematical claims
remain separate proof-graph work.

For source-level public roots, the generated module must not hide shallow
expansion as an arbitrary theorem premise. The generator constructs source
return structures from the JIT public StableHLO return leaves and emits
`sourceInitialize`, `sourceAlgorithmRun`, `sourceResidualWithinTolerance`, and
`sourceMain` as Lean definitions. The coverage theorem records
`sourceMainValueExpanded = true`. Proof themes consume those
definitions as the source value layer, then add theorem-specific numerical
claims separately.
Visible public-input configuration leaves are also emitted as structured source
types when they are part of the root data flow. For PDIPM-style roots this
includes `InitializeConfig.kkt_default_solve_config`: the generated
`SourceKktSolveConfig` records the public leaves that the implementation
passes into `SolveConfig.kkt_solve`, instead of leaving the KKT solve config as
an opaque proof-only value.
