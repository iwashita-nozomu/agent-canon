<!--
@dependency-start
contract reference
responsibility Documents agent-canon jit-ir-to-lean usage and current Lean output boundary.
downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR JSON into Lean evidence definitions.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py produces the consumed JIT-canonical IR JSON.
@dependency-end
-->

# jit-ir-to-lean

`agent-canon jit-ir-to-lean` converts JIT-canonical IR JSON into a generated
Lean evidence module. It is an AgentCanon Rust CLI command.

## Reader Map

Use this tool note to answer how `agent-canon jit-ir-to-lean` is invoked, what
Lean evidence it currently emits, and where the command boundary ends. Read
Command first for required inputs and output path, then Current Lean Output for
generated definitions and theorem shapes. Boundary states what the generated
module does not prove or own.

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
- `StablehloValueState`, `StablehloValueSemantics`, `stepStablehloValue`, and
  `runStablehloValueFuel`, a value-level recurrence over the same generated
  function / region / operation graph. The value type is a parameter `α`, so
  proof themes can instantiate it with real values, rounded-float models, or
  symbolic terms;
- `StablehloInputLeaves` and `generatedMainStablehloValueFromLeaves`, connecting
  public StableHLO argument leaves to the generated value recurrence without
  injecting theorem-specific values into production code;
- `SourceValueProblem α`, `sourceValueStablehloInputLeaves`, and
  `sourceProblemProjectionFromValueProblem`, connecting value-carrying public
  problem members to the generated StableHLO value recurrence while preserving
  the separate source-return projection surface;
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
function/region/op graph is available as Lean functions parameterized by
primitive semantics. The value-level recurrence is generated from StableHLO /
MLIR SSA rows (`resultNames`, `operandNames`, functions, regions, and expansion
edges); theorem files choose the semantic model for primitives instead of
hard-coding algorithm-specific formulas in the generator.

## StableHLO Value Recurrence Boundary

The generated StableHLO value recurrence follows the StableHLO / MLIR
operational shape and deliberately stops before theorem-specific mathematics:

- function bodies, `while` cond/body regions, `case` branches, calls, returns,
  and primitive rows are replayed from `OperationalProgram`;
- primitive values are produced by `StablehloValueSemantics.evalPrimitive`;
- dynamic control-flow branch selection is supplied by
  `StablehloValueSemantics.selectWhileBody` and
  `StablehloValueSemantics.selectCaseBranch`;
- input leaves are passed through `StablehloInputLeaves`, whose binding names
  must match the public StableHLO argument leaves;
- value-carrying public problem leaves can be converted by
  `sourceValueStablehloInputLeaves`, so theorem routes do not need arbitrary
  theorem-local input leaf witnesses;
- return values come from the generated `return` operand list, not from a
  hand-written theorem path.

The generator may parse MLIR SSA syntax (`%name = ...` and `return %x, ...`) and
the StableHLO control-region structure because those are implementation syntax
preserved in the compiler IR. It must not add domain labels such as KKT
regularity, direction quality, residual decrease, certificate soundness, or
problem-class assumptions. Those are theorem-graph claims over the generated
functions.

Reference specifications used by this boundary:

- StableHLO specification: https://openxla.org/stablehlo/spec
- LLVM Language Reference: https://llvm.org/docs/LangRef.html

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

The command does not emit:

- concrete semantics for `stablehlo.add`, `stablehlo.reduce`, tensor memory, or
  other numeric primitives. It emits the recurrence and a semantic hook for
  them;
- a concrete LLVM memory model or floating-point rounding model;
- theorem-specific claims such as progress, regularity, direction quality,
  certificate soundness, or termination.

Proof themes must cite the generated module as implementation provenance. The
generated `OperationalProgram` and `generatedMainFuel` are the Lean-side
reproduction of the JIT-lowered implementation shape and its fuelled
function/region/op composition. If backend trace data is present, the generated
LLVM runtime functions replay backend instruction rows as Lean functions.
Concrete numeric primitive semantics and theorem-specific mathematical claims
remain separate proof-graph work. Backend traces and LLVM instruction replay
provide the implementation witness for floating-point execution; they are not
used to rewrite the StableHLO recurrence itself.

For source-level public roots, the generated module separates public return
projection from value-level StableHLO execution. The generator constructs source
return structures from the JIT public StableHLO return leaves and emits
`sourceInitialize`, `sourceAlgorithmRun`, `sourceResidualOperandPathMatches`, and
`sourceMain` as Lean definitions. It also emits a value-level source run backed
by `generatedMainStablehloValueFromLeaves`, so proof themes can connect public
problem values to the generated recurrence without hand-written execution
adapters. The coverage theorem records both layers:

```lean
sourceMainProjectionCoverageClosed = true
sourceMainValueProjectionCoverageClosed = true
```

`sourceMainProjectionCoverageClosed = true` means the public root, public argument
tree, return roots, return leaves, and source call shape are represented.
`sourceMainValueProjectionCoverageClosed = true` means the generator emitted a value-carrying
route from public problem values to the generated StableHLO recurrence. The
source return projection is still not itself decoded numeric execution; numeric
proofs should use the value-level route and explicitly supply or derive the
primitive semantics needed by the theorem graph.
For roots with public problem tensor leaves, the generator also emits
`SourceValueProblem α` and `sourceValueStablehloInputLeaves`. Formal proof
routes that need numeric conditions over `Problem` members should use that
value-carrying adapter, then project back to the source-return surface with
`sourceProblemProjectionFromValueProblem` when a public-return theorem is stated
over `sourceMain`.
Visible public-input configuration leaves are also emitted as structured source
types when they are part of the root data flow. For PDIPM-style roots this
includes `InitializeConfig.default_stopping_config`: the generated
`SourceStoppingSolveConfig` records the public stopping leaves that the proof
root projects into `SolveConfig.stopping`, instead of leaving solve policy as
an opaque proof-only value.
