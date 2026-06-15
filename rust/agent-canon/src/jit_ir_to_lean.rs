// @dependency-start
// responsibility Lowers JIT-canonical operational IR JSON into Lean evidence definitions.
// upstream implementation ../../../tools/agent_tools/jit_canonical_ir.py emits StableHLO-derived thin IR.
// upstream design ../../../documents/tools/jit_ir_to_lean.md defines the JSON-to-Lean evidence boundary.
// downstream implementation main.rs exposes jit-ir-to-lean.
// @dependency-end

use serde_json::Value;
use std::fs;
use std::path::PathBuf;

#[derive(Debug)]
struct Args {
    jit_ir: PathBuf,
    namespace: String,
    module_name: String,
    out: PathBuf,
}

pub fn run(argv: &[String]) -> i32 {
    match parse_args(argv).and_then(run_checked) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("jit-ir-to-lean: {error}");
            2
        }
    }
}

fn parse_args(argv: &[String]) -> Result<Args, String> {
    let mut jit_ir: Option<PathBuf> = None;
    let mut namespace: Option<String> = None;
    let mut module_name: Option<String> = None;
    let mut out: Option<PathBuf> = None;
    let mut index = 0;
    while index < argv.len() {
        match argv[index].as_str() {
            "--jit-ir" => {
                index += 1;
                jit_ir = argv.get(index).map(PathBuf::from);
            }
            "--namespace" => {
                index += 1;
                namespace = argv.get(index).cloned();
            }
            "--module-name" => {
                index += 1;
                module_name = argv.get(index).cloned();
            }
            "--out" => {
                index += 1;
                out = argv.get(index).map(PathBuf::from);
            }
            "--help" | "-h" => return Err(usage()),
            other => return Err(format!("unknown argument {other:?}\n{}", usage())),
        }
        index += 1;
    }
    Ok(Args {
        jit_ir: jit_ir.ok_or_else(usage)?,
        namespace: namespace.ok_or_else(usage)?,
        module_name: module_name.unwrap_or_else(|| "jit_canonical".to_string()),
        out: out.ok_or_else(usage)?,
    })
}

fn usage() -> String {
    "usage: agent-canon jit-ir-to-lean --jit-ir <path> --namespace <Lean.Namespace> [--module-name name] --out <path>".to_string()
}

fn run_checked(args: Args) -> Result<(), String> {
    let input = fs::read_to_string(&args.jit_ir)
        .map_err(|error| format!("cannot read {}: {error}", args.jit_ir.display()))?;
    let value: Value = serde_json::from_str(&input)
        .map_err(|error| format!("invalid JSON {}: {error}", args.jit_ir.display()))?;
    let rendered = render_lean(&args, &value)?;
    if let Some(parent) = args.out.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(&args.out, rendered)
        .map_err(|error| format!("cannot write {}: {error}", args.out.display()))?;
    Ok(())
}

fn render_lean(args: &Args, value: &Value) -> Result<String, String> {
    let root = value
        .get("root")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing root object".to_string())?;
    let stablehlo = value
        .get("stablehlo")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing stablehlo object".to_string())?;
    let operational = value
        .get("operational_ir")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing operational_ir object".to_string())?;
    let backend = value.get("backend_trace").and_then(Value::as_object);
    let include_backend = backend.is_some();
    let source_root = value.get("source_root").and_then(Value::as_object);
    let source_root_hlo_only = source_root_is_hlo_only(source_root);
    let public_interface = value
        .get("public_interface")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing public_interface object".to_string())?;
    require_string_field(
        public_interface,
        "schema",
        "agent-canon.public-interface.v1",
        "public_interface.schema",
    )?;
    public_interface
        .get("return_roots")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing public_interface.return_roots array".to_string())?;
    public_interface
        .get("return_leaves")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing public_interface.return_leaves array".to_string())?;
    public_interface
        .get("coverage")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing public_interface.coverage object".to_string())?;
    let public_coverage = public_interface
        .get("coverage")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing public_interface.coverage object".to_string())?;
    require_bool_field(
        public_coverage,
        "has_answer_state_info_return",
        true,
        "public_interface.coverage.has_answer_state_info_return",
    )?;
    let ops = operational
        .get("ops")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing operational_ir.ops array".to_string())?;
    let functions = operational.get("functions").and_then(Value::as_array);
    let regions = operational.get("regions").and_then(Value::as_array);
    let expansion_edges = operational.get("expansion_edges").and_then(Value::as_array);
    let coverage = operational.get("coverage").and_then(Value::as_object);
    let allowed = operational
        .get("allowed_kinds")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing operational_ir.allowed_kinds array".to_string())?;

    let mut lines = Vec::new();
    lines.push("/-".to_string());
    lines.push("@dependency-start".to_string());
    lines.push(format!(
        "responsibility Generated Lean evidence for JIT-canonical function {}.",
        string_field(root, "python_symbol")
    ));
    lines.push(format!(
        "upstream implementation ../{} JIT-canonical IR JSON consumed by this generated file.",
        args.jit_ir
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("jit_ir.json")
    ));
    lines.push("@dependency-end".to_string());
    lines.push("-/".to_string());
    lines.push(String::new());
    lines.push("set_option maxRecDepth 100000".to_string());
    lines.push(String::new());
    lines.push(format!("namespace {}", args.namespace));
    lines.push(format!(
        "namespace {}",
        sanitize_namespace(&args.module_name)
    ));
    lines.push(String::new());
    lines.extend([
        "structure OperationalOp where".to_string(),
        "  opId : String".to_string(),
        "  kind : String".to_string(),
        "  opcode : String".to_string(),
        "  line : Nat".to_string(),
        "  textSha256 : String".to_string(),
        "  dtypes : List String".to_string(),
        "  functionName : String".to_string(),
        "  regionId : String".to_string(),
        "  parentOpId : String".to_string(),
        "  callTarget : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalFunction where".to_string(),
        "  functionId : String".to_string(),
        "  name : String".to_string(),
        "  signature : String".to_string(),
        "  lineStart : Nat".to_string(),
        "  lineEnd : Nat".to_string(),
        "  bodyRegionId : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalRegion where".to_string(),
        "  regionId : String".to_string(),
        "  kind : String".to_string(),
        "  parentFunction : String".to_string(),
        "  parentOpId : String".to_string(),
        "  depth : Nat".to_string(),
        "  lineStart : Nat".to_string(),
        "  lineEnd : Nat".to_string(),
        "  opIds : List String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure ExpansionEdge where".to_string(),
        "  edgeId : String".to_string(),
        "  kind : String".to_string(),
        "  fromId : String".to_string(),
        "  toId : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalProgram where".to_string(),
        "  entryFunction : String".to_string(),
        "  functions : List OperationalFunction".to_string(),
        "  regions : List OperationalRegion".to_string(),
        "  expansionEdges : List ExpansionEdge".to_string(),
        "  opCount : Nat".to_string(),
        "  regionCount : Nat".to_string(),
        "  expansionEdgeCount : Nat".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalCoverage where".to_string(),
        "  functionCount : Nat".to_string(),
        "  regionCount : Nat".to_string(),
        "  expansionEdgeCount : Nat".to_string(),
        "  opCount : Nat".to_string(),
        "  unassignedOpCount : Nat".to_string(),
        "  maxRegionDepth : Nat".to_string(),
        "  whileCount : Nat".to_string(),
        "  caseCount : Nat".to_string(),
        "  ifCount : Nat".to_string(),
        "  callCount : Nat".to_string(),
        "  unresolvedCallTargets : List String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure PublicRoot where".to_string(),
        "  index : Nat".to_string(),
        "  label : String".to_string(),
        "  annotation : String".to_string(),
        "  path : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure PublicLeaf where".to_string(),
        "  leafIndex : Nat".to_string(),
        "  rootIndex : Nat".to_string(),
        "  rootName : String".to_string(),
        "  path : String".to_string(),
        "  localPath : String".to_string(),
        "  pythonType : String".to_string(),
        "  shape : String".to_string(),
        "  dtype : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure StablehloPublicLeaf where".to_string(),
        "  leafIndex : Nat".to_string(),
        "  name : String".to_string(),
        "  stablehloType : String".to_string(),
        "  resultInfo : String".to_string(),
        "  resultIndexes : List Nat".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure PublicInterfaceCoverage where".to_string(),
        "  argumentRootCount : Nat".to_string(),
        "  argumentLeafCount : Nat".to_string(),
        "  returnRootCount : Nat".to_string(),
        "  returnLeafCount : Nat".to_string(),
        "  stablehloArgumentCount : Nat".to_string(),
        "  stablehloReturnLeafCount : Nat".to_string(),
        "  hasAnswerStateInfoReturn : Bool".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure PublicInterface where".to_string(),
        "  pythonSymbol : String".to_string(),
        "  returnAnnotation : String".to_string(),
        "  argumentRoots : List PublicRoot".to_string(),
        "  argumentLeaves : List PublicLeaf".to_string(),
        "  returnRoots : List PublicRoot".to_string(),
        "  returnLeaves : List PublicLeaf".to_string(),
        "  stablehloArguments : List StablehloPublicLeaf".to_string(),
        "  stablehloReturnLeaves : List StablehloPublicLeaf".to_string(),
        "  coverage : PublicInterfaceCoverage".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
    ]);

    if include_backend {
        lines.extend([
            "structure LlvmCount where".to_string(),
            "  key : String".to_string(),
            "  count : Nat".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmBasicBlockTrace where".to_string(),
            "  label : String".to_string(),
            "  line : Nat".to_string(),
            "  instructionIds : List String".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmInstructionTrace where".to_string(),
            "  instructionId : String".to_string(),
            "  functionName : String".to_string(),
            "  basicBlock : String".to_string(),
            "  line : Nat".to_string(),
            "  resultName : String".to_string(),
            "  opcode : String".to_string(),
            "  operandText : String".to_string(),
            "  text : String".to_string(),
            "  textSha256 : String".to_string(),
            "  fastMathFlags : List String".to_string(),
            "  isFloatOp : Bool".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmFunctionTrace where".to_string(),
            "  name : String".to_string(),
            "  signature : String".to_string(),
            "  returnAndAttrs : String".to_string(),
            "  params : String".to_string(),
            "  opCounts : List LlvmCount".to_string(),
            "  fastMathFlags : List LlvmCount".to_string(),
            "  basicBlockLabels : List String".to_string(),
            "  instructionIds : List String".to_string(),
            "  instructionCount : Nat".to_string(),
            "  floatInstructionCount : Nat".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmModuleTrace where".to_string(),
            "  path : String".to_string(),
            "  sha256 : String".to_string(),
            "  kind : String".to_string(),
            "  functionCount : Nat".to_string(),
            "  basicBlockCount : Nat".to_string(),
            "  instructionCount : Nat".to_string(),
            "  floatInstructionCount : Nat".to_string(),
            "  opCounts : List LlvmCount".to_string(),
            "  fastMathFlags : List LlvmCount".to_string(),
            "  functions : List LlvmFunctionTrace".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmRuntimeValue where".to_string(),
            "  text : String".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmRuntimeBinding where".to_string(),
            "  name : String".to_string(),
            "  value : LlvmRuntimeValue".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmRuntimeState where".to_string(),
            "  bindings : List LlvmRuntimeBinding".to_string(),
            "  currentFunction : String".to_string(),
            "  currentBlock : String".to_string(),
            "  previousBlock : String".to_string(),
            "  executedInstructionIds : List String".to_string(),
            "  traceOpcodes : List String".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
            "structure LlvmPrimitiveSemantics where".to_string(),
            "  evalInstruction : LlvmRuntimeState -> LlvmInstructionTrace -> LlvmRuntimeValue"
                .to_string(),
            String::new(),
            "structure BackendTrace where".to_string(),
            "  coverage : String".to_string(),
            "  targetBackend : String".to_string(),
            "  ireeCompileAvailable : Bool".to_string(),
            "  ireeRunModuleAvailable : Bool".to_string(),
            "  lastSuccessfulPhase : String".to_string(),
            "  phaseTraceCount : Nat".to_string(),
            "  compileAttemptCount : Nat".to_string(),
            "  llvmModuleCount : Nat".to_string(),
            "  llvmBitcodeCount : Nat".to_string(),
            "  executableSourceCount : Nat".to_string(),
            "  llvmModules : List LlvmModuleTrace".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
        ]);
    }

    if !source_root_hlo_only {
        lines.extend([
            "structure SourceRoot where".to_string(),
            "  pythonSymbol : String".to_string(),
            "  path : String".to_string(),
            "  qualname : String".to_string(),
            "  name : String".to_string(),
            "  parameters : List String".to_string(),
            "  returnAnnotation : String".to_string(),
            "  sourceSha256 : String".to_string(),
            "  pattern : String".to_string(),
            "deriving Repr, DecidableEq".to_string(),
            String::new(),
        ]);
    }

    lines.extend([
        "structure JitCanonicalFunction where".to_string(),
        "  pythonSymbol : String".to_string(),
        "  inputFactorySymbol : String".to_string(),
    ]);
    if !source_root_hlo_only {
        lines.push("  sourceRoot : SourceRoot".to_string());
    }
    lines.extend([
        "  stablehloSha256 : String".to_string(),
        "  stablehloDialect : String".to_string(),
        "  allowedKinds : List String".to_string(),
        "  ops : List OperationalOp".to_string(),
        "  program : OperationalProgram".to_string(),
        "  coverage : OperationalCoverage".to_string(),
        "  publicInterface : PublicInterface".to_string(),
    ]);
    if include_backend {
        lines.push("  backend : BackendTrace".to_string());
    }
    lines.extend(["deriving Repr, DecidableEq".to_string(), String::new()]);

    lines.push("def allowedKinds : List String :=".to_string());
    lines.push(render_string_list(allowed, "  "));
    lines.push(String::new());
    lines.push("noncomputable def operationalOps : List OperationalOp :=".to_string());
    if ops.is_empty() {
        lines.push("  []".to_string());
    } else {
        lines.push("  [".to_string());
        for (index, op) in ops.iter().enumerate() {
            let comma = if index + 1 == ops.len() { "" } else { "," };
            let line_value = op.get("line").and_then(Value::as_u64).unwrap_or(0);
            lines.push(format!(
                "    {{ opId := {}, kind := {}, opcode := {}, line := {}, textSha256 := {}, dtypes := {}, functionName := {}, regionId := {}, parentOpId := {}, callTarget := {} }}{}",
                lean_string(value_field(op, "op_id")),
                lean_string(value_field(op, "kind")),
                lean_string(value_field(op, "opcode")),
                line_value,
                lean_string(value_field(op, "text_sha256")),
                render_inline_string_list(op.get("dtypes").and_then(Value::as_array)),
                lean_string(value_field(op, "function")),
                lean_string(value_field(op, "region_id")),
                lean_string(value_field(op, "parent_op_id")),
                lean_string(value_field(op, "call_target")),
                comma
            ));
        }
        lines.push("  ]".to_string());
    }
    lines.push(String::new());

    lines.push("def operationalFunctions : List OperationalFunction :=".to_string());
    lines.push(render_operational_functions(functions));
    lines.push(String::new());
    lines.push("def operationalRegions : List OperationalRegion :=".to_string());
    lines.push(render_operational_regions(regions));
    lines.push(String::new());
    lines.push("def expansionEdges : List ExpansionEdge :=".to_string());
    lines.push(render_expansion_edges(expansion_edges));
    lines.push(String::new());
    lines.push("noncomputable def operationalProgram : OperationalProgram :=".to_string());
    lines.push(format!(
        "  {{ entryFunction := {}, functions := operationalFunctions, regions := operationalRegions, expansionEdges := expansionEdges, opCount := operationalOps.length, regionCount := operationalRegions.length, expansionEdgeCount := expansionEdges.length }}",
        lean_string(entry_function_name(functions))
    ));
    lines.push(String::new());
    lines.push("def operationalCoverage : OperationalCoverage :=".to_string());
    lines.push(render_operational_coverage(coverage));
    lines.push(String::new());
    lines.extend(render_operational_evaluator());
    lines.push(String::new());
    lines.push("def publicArgumentRoots : List PublicRoot :=".to_string());
    lines.push(render_public_roots(
        Some(public_interface),
        "argument_roots",
        "name",
    ));
    lines.push(String::new());
    lines.push("def publicArgumentLeaves : List PublicLeaf :=".to_string());
    lines.push(render_public_leaves(
        Some(public_interface),
        "argument_leaves",
    ));
    lines.push(String::new());
    lines.push("def publicReturnRoots : List PublicRoot :=".to_string());
    lines.push(render_public_roots(
        Some(public_interface),
        "return_roots",
        "label",
    ));
    lines.push(String::new());
    lines.push("def publicReturnLeaves : List PublicLeaf :=".to_string());
    lines.push(render_public_leaves(
        Some(public_interface),
        "return_leaves",
    ));
    lines.push(String::new());
    lines.push("def publicStablehloArguments : List StablehloPublicLeaf :=".to_string());
    lines.push(render_stablehlo_public_leaves(
        Some(public_interface),
        &["stablehlo_entry", "arguments"],
        false,
    ));
    lines.push(String::new());
    lines.push("def publicStablehloReturnLeaves : List StablehloPublicLeaf :=".to_string());
    lines.push(render_stablehlo_public_leaves(
        Some(public_interface),
        &["stablehlo_entry", "return_leaves"],
        true,
    ));
    lines.push(String::new());
    lines.push("def publicInterfaceCoverage : PublicInterfaceCoverage :=".to_string());
    lines.push(render_public_interface_coverage(Some(public_interface)));
    lines.push(String::new());
    lines.push("def publicInterface : PublicInterface :=".to_string());
    lines.push(format!(
        "  {{ pythonSymbol := {}, returnAnnotation := {}, argumentRoots := publicArgumentRoots, argumentLeaves := publicArgumentLeaves, returnRoots := publicReturnRoots, returnLeaves := publicReturnLeaves, stablehloArguments := publicStablehloArguments, stablehloReturnLeaves := publicStablehloReturnLeaves, coverage := publicInterfaceCoverage }}",
        lean_string(
            public_interface
                .get("python_symbol")
                .and_then(Value::as_str)
                .unwrap_or("")
        ),
        lean_string(
            public_interface
                .get("return_annotation")
                .and_then(Value::as_str)
                .unwrap_or("")
        ),
    ));
    lines.push(String::new());
    lines.push("def publicReturnRootLabels : List String :=".to_string());
    lines.push("  publicReturnRoots.map (fun root => root.label)".to_string());
    lines.push(String::new());
    lines.push("def publicReturnLeafPaths : List String :=".to_string());
    lines.push("  publicReturnLeaves.map (fun leaf => leaf.path)".to_string());
    lines.push(String::new());
    lines.push("def publicAnswerLeafPaths : List String :=".to_string());
    lines.push("  (publicReturnLeaves.filter (fun leaf => leaf.rootName == \"answer\")).map (fun leaf => leaf.path)".to_string());
    lines.push(String::new());
    lines.push("def publicStateLeafPaths : List String :=".to_string());
    lines.push("  (publicReturnLeaves.filter (fun leaf => leaf.rootName == \"state\")).map (fun leaf => leaf.path)".to_string());
    lines.push(String::new());
    lines.push("def publicInfoLeafPaths : List String :=".to_string());
    lines.push("  (publicReturnLeaves.filter (fun leaf => leaf.rootName == \"info\")).map (fun leaf => leaf.path)".to_string());
    lines.push(String::new());

    let mut llvm_basic_block_count = 0usize;
    let mut llvm_instruction_count = 0usize;
    if let Some(backend) = backend {
        let executables = backend
            .get("executables")
            .and_then(Value::as_object)
            .ok_or_else(|| "missing backend_witness.executables object".to_string())?;
        let llvm_modules = backend.get("llvm_ir").and_then(Value::as_array);
        let llvm_bitcode_count = backend
            .get("llvm_bitcode")
            .and_then(Value::as_array)
            .map_or(0, |items| items.len());
        let source_count = backend
            .get("executable_sources")
            .and_then(Value::as_array)
            .map_or(0, |items| items.len());
        let phase_trace_count = backend
            .get("phase_traces")
            .and_then(Value::as_array)
            .map_or(0, |items| items.len());
        let compile_attempt_count = backend
            .get("compile_attempts")
            .and_then(Value::as_array)
            .map_or(0, |items| items.len());
        let llvm_basic_block_values = collect_llvm_basic_blocks(llvm_modules);
        let llvm_instruction_values = collect_llvm_instructions(llvm_modules);
        llvm_basic_block_count = llvm_basic_block_values.len();
        llvm_instruction_count = llvm_instruction_values.len();
        lines.push("def llvmModules : List LlvmModuleTrace :=".to_string());
        lines.push(render_llvm_modules(llvm_modules));
        lines.push(String::new());
        lines.push("def llvmBasicBlocks : List LlvmBasicBlockTrace :=".to_string());
        lines.push(render_llvm_basic_blocks(Some(&llvm_basic_block_values)));
        lines.push(String::new());
        lines.push("def llvmInstructions : List LlvmInstructionTrace :=".to_string());
        lines.push(render_llvm_instructions(Some(&llvm_instruction_values)));
        lines.push(String::new());
        lines.extend([
            "def symbolicLlvmPrimitiveSemantics : LlvmPrimitiveSemantics :=".to_string(),
            "  { evalInstruction := fun _ inst => { text := inst.textSha256 } }".to_string(),
            String::new(),
            "def initialLlvmRuntimeState : LlvmRuntimeState :=".to_string(),
            "  { bindings := [], currentFunction := \"\", currentBlock := \"\", previousBlock := \"\", executedInstructionIds := [], traceOpcodes := [] }".to_string(),
            String::new(),
            "def updateLlvmRuntimeBindings (bindings : List LlvmRuntimeBinding) (name : String) (value : LlvmRuntimeValue) : List LlvmRuntimeBinding :=".to_string(),
            "  if name = \"\" then bindings else { name := name, value := value } :: bindings".to_string(),
            String::new(),
            "def executeLlvmInstruction (semantics : LlvmPrimitiveSemantics) (state : LlvmRuntimeState) (inst : LlvmInstructionTrace) : LlvmRuntimeState :=".to_string(),
            "  let value := semantics.evalInstruction state inst".to_string(),
            "  { state with".to_string(),
            "    bindings := updateLlvmRuntimeBindings state.bindings inst.resultName value,".to_string(),
            "    currentFunction := inst.functionName,".to_string(),
            "    previousBlock := state.currentBlock,".to_string(),
            "    currentBlock := inst.basicBlock,".to_string(),
            "    executedInstructionIds := state.executedInstructionIds ++ [inst.instructionId],".to_string(),
            "    traceOpcodes := state.traceOpcodes ++ [inst.opcode] }".to_string(),
            String::new(),
            "def runLlvmInstructions (semantics : LlvmPrimitiveSemantics) (state : LlvmRuntimeState) : List LlvmInstructionTrace -> LlvmRuntimeState".to_string(),
            "  | [] => state".to_string(),
            "  | inst :: rest => runLlvmInstructions semantics (executeLlvmInstruction semantics state inst) rest".to_string(),
            String::new(),
            "def generatedLlvmRuntimeState : LlvmRuntimeState :=".to_string(),
            "  runLlvmInstructions symbolicLlvmPrimitiveSemantics initialLlvmRuntimeState llvmInstructions".to_string(),
            String::new(),
            "theorem executeLlvmInstruction_records_one_instruction".to_string(),
            "    (semantics : LlvmPrimitiveSemantics)".to_string(),
            "    (state : LlvmRuntimeState)".to_string(),
            "    (inst : LlvmInstructionTrace) :".to_string(),
            "    (executeLlvmInstruction semantics state inst).executedInstructionIds.length".to_string(),
            "      = state.executedInstructionIds.length + 1 := by".to_string(),
            "  simp [executeLlvmInstruction]".to_string(),
            String::new(),
            "theorem runLlvmInstructions_records_all_instructions".to_string(),
            "    (semantics : LlvmPrimitiveSemantics)".to_string(),
            "    (state : LlvmRuntimeState)".to_string(),
            "    (instructions : List LlvmInstructionTrace) :".to_string(),
            "    (runLlvmInstructions semantics state instructions).executedInstructionIds.length".to_string(),
            "      = state.executedInstructionIds.length + instructions.length := by".to_string(),
            "  induction instructions generalizing state with".to_string(),
            "  | nil =>".to_string(),
            "      simp [runLlvmInstructions]".to_string(),
            "  | cons inst rest ih =>".to_string(),
            "      simp [runLlvmInstructions, ih, executeLlvmInstruction, Nat.add_comm, Nat.add_left_comm]".to_string(),
            String::new(),
            "theorem generated_llvm_runtime_records_all_instructions :".to_string(),
            "    generatedLlvmRuntimeState.executedInstructionIds.length = llvmInstructions.length := by".to_string(),
            "  simp [generatedLlvmRuntimeState, initialLlvmRuntimeState, runLlvmInstructions_records_all_instructions]".to_string(),
            String::new(),
        ]);
        lines.push("def backendTrace : BackendTrace :=".to_string());
        lines.push(format!(
            "  {{ coverage := {}, targetBackend := {}, ireeCompileAvailable := {}, ireeRunModuleAvailable := {}, lastSuccessfulPhase := {}, phaseTraceCount := {}, compileAttemptCount := {}, llvmModuleCount := llvmModules.length, llvmBitcodeCount := {}, executableSourceCount := {}, llvmModules := llvmModules }}",
            lean_string(string_field(backend, "coverage")),
            lean_string(string_field(backend, "target_backend")),
            executables.get("iree-compile").is_some_and(|v| !v.is_null()),
            executables.get("iree-run-module").is_some_and(|v| !v.is_null()),
            lean_string(string_field(backend, "last_successful_phase")),
            phase_trace_count,
            compile_attempt_count,
            llvm_bitcode_count,
            source_count
        ));
        lines.push(String::new());
    }
    if !source_root_hlo_only {
        lines.push("def sourceRoot : SourceRoot :=".to_string());
        lines.push(render_source_root(source_root));
        lines.push(String::new());
    }
    if !source_root_hlo_only && source_root_has_main_pattern(source_root) {
        lines.extend(render_source_main_boundary(
            source_root,
            Some(public_interface),
        ));
        lines.push(String::new());
    }
    lines.push("noncomputable def generatedFunction : JitCanonicalFunction :=".to_string());
    let backend_field = if include_backend {
        ", backend := backendTrace"
    } else {
        ""
    };
    if source_root_hlo_only {
        lines.push(format!(
            "  {{ pythonSymbol := {}, inputFactorySymbol := {}, stablehloSha256 := {}, stablehloDialect := {}, allowedKinds := allowedKinds, ops := operationalOps, program := operationalProgram, coverage := operationalCoverage, publicInterface := publicInterface{} }}",
            lean_string(string_field(root, "python_symbol")),
            lean_string(string_field(root, "input_factory_symbol")),
            lean_string(string_field(stablehlo, "sha256")),
            lean_string(string_field(stablehlo, "dialect")),
            backend_field,
        ));
    } else {
        lines.push(format!(
            "  {{ pythonSymbol := {}, inputFactorySymbol := {}, sourceRoot := sourceRoot, stablehloSha256 := {}, stablehloDialect := {}, allowedKinds := allowedKinds, ops := operationalOps, program := operationalProgram, coverage := operationalCoverage, publicInterface := publicInterface{} }}",
            lean_string(string_field(root, "python_symbol")),
            lean_string(string_field(root, "input_factory_symbol")),
            lean_string(string_field(stablehlo, "sha256")),
            lean_string(string_field(stablehlo, "dialect")),
            backend_field,
        ));
    }
    lines.push(String::new());
    lines.push("theorem generatedFunction_root :".to_string());
    lines.push(format!(
        "    generatedFunction.pythonSymbol = {} := by",
        lean_string(string_field(root, "python_symbol"))
    ));
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_public_interface_root :".to_string());
    lines.push(
        "    generatedFunction.publicInterface.pythonSymbol = generatedFunction.pythonSymbol := by"
            .to_string(),
    );
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_public_return_root_labels :".to_string());
    lines.push(format!(
        "    publicReturnRootLabels = {} := by",
        render_public_root_labels(Some(public_interface))
    ));
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_public_return_leaf_paths :".to_string());
    lines.push(format!(
        "    publicReturnLeafPaths = {} := by",
        render_public_leaf_paths(Some(public_interface))
    ));
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_public_return_leaf_count_matches :".to_string());
    lines.push("    generatedFunction.publicInterface.coverage.returnLeafCount = publicReturnLeaves.length := by".to_string());
    lines.push("  rfl".to_string());
    lines.push(String::new());
    if !source_root_hlo_only {
        lines.push("theorem generatedFunction_source_root_matches :".to_string());
        lines.push(
            "    generatedFunction.sourceRoot.pythonSymbol = generatedFunction.pythonSymbol := by"
                .to_string(),
        );
        lines.push("  rfl".to_string());
        lines.push(String::new());
    }
    lines.push("theorem generatedFunction_stablehlo_hash :".to_string());
    lines.push(format!(
        "    generatedFunction.stablehloSha256 = {} := by",
        lean_string(string_field(stablehlo, "sha256"))
    ));
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_function_lowering_coverage_verified :".to_string());
    lines.push("    generatedFunction.program.opCount = generatedFunction.ops.length".to_string());
    lines.push(
        "      ∧ generatedFunction.program.regionCount = operationalRegions.length".to_string(),
    );
    lines.push(
        "      ∧ generatedFunction.program.expansionEdgeCount = expansionEdges.length := by"
            .to_string(),
    );
    lines.push("  constructor".to_string());
    lines.push("  · rfl".to_string());
    lines.push("  constructor".to_string());
    lines.push("  · rfl".to_string());
    lines.push("  · rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_function_no_unassigned_ops :".to_string());
    lines.push("    generatedFunction.coverage.unassignedOpCount = 0 := by".to_string());
    lines.push("  rfl".to_string());
    lines.push(String::new());
    lines.push("theorem generated_function_no_unresolved_calls :".to_string());
    lines.push("    generatedFunction.coverage.unresolvedCallTargets = [] := by".to_string());
    lines.push("  rfl".to_string());
    lines.push(String::new());
    if include_backend {
        lines.push("theorem generated_backend_llvm_count_matches :".to_string());
        lines.push(
            "    generatedFunction.backend.llvmModuleCount = llvmModules.length := by".to_string(),
        );
        lines.push("  rfl".to_string());
        lines.push(String::new());
        lines.push("theorem generated_backend_llvm_basic_block_count_matches :".to_string());
        lines.push(format!(
            "    llvmBasicBlocks.length = {} := by",
            llvm_basic_block_count
        ));
        lines.push("  rfl".to_string());
        lines.push(String::new());
        lines.push("theorem generated_backend_llvm_instruction_count_matches :".to_string());
        lines.push(format!(
            "    llvmInstructions.length = {} := by",
            llvm_instruction_count
        ));
        lines.push("  rfl".to_string());
        lines.push(String::new());
    }
    lines.push("noncomputable def replayTrace : List String :=".to_string());
    lines.push("  operationalOps.map (fun op => op.opId)".to_string());
    lines.push(String::new());
    lines.push("theorem replayTrace_covers_operationalOps :".to_string());
    lines.push("    replayTrace.length = operationalOps.length := by".to_string());
    lines.push("  simp [replayTrace]".to_string());
    lines.push(String::new());
    lines.push(format!("end {}", sanitize_namespace(&args.module_name)));
    lines.push(format!("end {}", args.namespace));
    lines.push(String::new());
    Ok(lines.join("\n"))
}

fn require_string_field(
    object: &serde_json::Map<String, Value>,
    key: &str,
    expected: &str,
    label: &str,
) -> Result<(), String> {
    let actual = object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing {label} string"))?;
    if actual != expected {
        return Err(format!("expected {label} = {expected:?}, got {actual:?}"));
    }
    Ok(())
}

fn require_bool_field(
    object: &serde_json::Map<String, Value>,
    key: &str,
    expected: bool,
    label: &str,
) -> Result<(), String> {
    let actual = object
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| format!("missing {label} bool"))?;
    if actual != expected {
        return Err(format!("expected {label} = {expected}, got {actual}"));
    }
    Ok(())
}

fn value_field<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("")
}

fn string_field(value: &serde_json::Map<String, Value>, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn source_string_field(value: Option<&serde_json::Map<String, Value>>, key: &str) -> String {
    value
        .and_then(|object| object.get(key))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn source_string_list(value: Option<&serde_json::Map<String, Value>>, key: &str) -> String {
    let values = value
        .and_then(|object| object.get(key))
        .and_then(Value::as_array);
    render_inline_string_list(values)
}

fn source_pattern(
    value: Option<&serde_json::Map<String, Value>>,
) -> Option<&serde_json::Map<String, Value>> {
    value
        .and_then(|object| object.get("main_pattern"))
        .and_then(Value::as_object)
}

fn source_root_has_main_pattern(value: Option<&serde_json::Map<String, Value>>) -> bool {
    source_pattern(value)
        .and_then(|pattern| pattern.get("pattern"))
        .and_then(Value::as_str)
        == Some("initialize_then_algorithm_call_return_tuple")
}

fn source_root_is_hlo_only(value: Option<&serde_json::Map<String, Value>>) -> bool {
    value
        .and_then(|object| object.get("status"))
        .and_then(Value::as_str)
        == Some("hlo_only")
}

fn pattern_value<'a>(
    pattern: Option<&'a serde_json::Map<String, Value>>,
    path: &[&str],
) -> Option<&'a Value> {
    let mut current = pattern?;
    for (index, key) in path.iter().enumerate() {
        let value = current.get(*key)?;
        if index + 1 == path.len() {
            return Some(value);
        }
        current = value.as_object()?;
    }
    None
}

fn pattern_string(pattern: Option<&serde_json::Map<String, Value>>, path: &[&str]) -> String {
    match pattern_value(pattern, path) {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(other) => other.to_string(),
        None => String::new(),
    }
}

fn pattern_nat(pattern: Option<&serde_json::Map<String, Value>>, path: &[&str]) -> u64 {
    pattern_value(pattern, path)
        .and_then(Value::as_u64)
        .unwrap_or(0)
}

fn render_source_root(value: Option<&serde_json::Map<String, Value>>) -> String {
    let pattern = source_pattern(value)
        .and_then(|object| object.get("pattern"))
        .and_then(Value::as_str)
        .unwrap_or("");
    format!(
        "  {{ pythonSymbol := {}, path := {}, qualname := {}, name := {}, parameters := {}, returnAnnotation := {}, sourceSha256 := {}, pattern := {} }}",
        lean_string(source_string_field(value, "python_symbol")),
        lean_string(source_string_field(value, "path")),
        lean_string(source_string_field(value, "qualname")),
        lean_string(source_string_field(value, "name")),
        source_string_list(value, "parameters"),
        lean_string(source_string_field(value, "return_annotation")),
        lean_string(source_string_field(value, "source_sha256")),
        lean_string(pattern),
    )
}

fn render_source_main_boundary(
    value: Option<&serde_json::Map<String, Value>>,
    public_interface: Option<&serde_json::Map<String, Value>>,
) -> Vec<String> {
    let pattern = source_pattern(value);
    let maxiter = pattern_nat(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "maxiter",
        ],
    );
    let squared = pattern_nat(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "squared",
        ],
    );
    let rtol = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "rtol",
        ],
    );
    let atol = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "atol",
        ],
    );
    let reference = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "reference",
        ],
    );
    let norm = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "norm",
        ],
    );
    let runtime_rtol = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "runtime_rtol",
        ],
    );
    let runtime_atol = pattern_string(
        pattern,
        &[
            "algorithm_call",
            "solve_config",
            "stopping_keywords",
            "runtime_atol",
        ],
    );
    let mut lines = vec![
        "/-- Source-level type boundary generated from the Python root function. -/".to_string(),
        "opaque SourceProblem : Type".to_string(),
        "opaque SourceFloat : Type".to_string(),
        "opaque SourceInt : Type".to_string(),
        "opaque SourceVector : Type".to_string(),
        "opaque SourceKktSolveConfig : Type".to_string(),
        String::new(),
    ];
    lines.extend(render_source_return_structures(public_interface));
    lines.extend([
        "structure SourceStoppingSolveConfig where".to_string(),
        "  maxiter : Nat".to_string(),
        "  rtol : String".to_string(),
        "  atol : String".to_string(),
        "  reference : String".to_string(),
        "  norm : String".to_string(),
        "  squared : Nat".to_string(),
        "  runtimeRtol : String".to_string(),
        "  runtimeAtol : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure SourceSolveConfig where".to_string(),
        "  kktSolve : SourceKktSolveConfig".to_string(),
        "  stopping : SourceStoppingSolveConfig".to_string(),
        String::new(),
        "structure SourceInitializeConfig where".to_string(),
        "  kktDefaultSolveConfig : SourceKktSolveConfig".to_string(),
        String::new(),
        "structure SourceAlgorithm where".to_string(),
        "  run : SourceProblem -> SourceState -> SourceSolveConfig -> SourceAnswer × SourceState × SourceInfo".to_string(),
        String::new(),
        "axiom sourceInitialize : SourceInitializeConfig -> SourceAlgorithm × SourceState".to_string(),
        String::new(),
        "def sourceStoppingSolveConfig : SourceStoppingSolveConfig :=".to_string(),
        format!(
            "  {{ maxiter := {}, rtol := {}, atol := {}, reference := {}, norm := {}, squared := {}, runtimeRtol := {}, runtimeAtol := {} }}",
            maxiter,
            lean_string(rtol),
            lean_string(atol),
            lean_string(reference),
            lean_string(norm),
            squared,
            lean_string(runtime_rtol),
            lean_string(runtime_atol),
        ),
        String::new(),
        "def sourceSolveConfig (initialize_config : SourceInitializeConfig) : SourceSolveConfig :=".to_string(),
        "  { kktSolve := initialize_config.kktDefaultSolveConfig, stopping := sourceStoppingSolveConfig }".to_string(),
        String::new(),
        "/-- Generated source-level Lean embedding of `main.py::main`. -/".to_string(),
        "noncomputable def sourceMain".to_string(),
        "    (problem : SourceProblem)".to_string(),
        "    (initialize_config : SourceInitializeConfig) : SourceAnswer × SourceState × SourceInfo :=".to_string(),
        "  let initialized := sourceInitialize initialize_config".to_string(),
        "  let algorithm := initialized.1".to_string(),
        "  let state := initialized.2".to_string(),
        "  let answer_next_state_info := algorithm.run problem state (sourceSolveConfig initialize_config)".to_string(),
        "  answer_next_state_info".to_string(),
        String::new(),
        "theorem sourceMain_embeds_python_main :".to_string(),
        "    sourceRoot.pattern = \"initialize_then_algorithm_call_return_tuple\" := by".to_string(),
        "  rfl".to_string(),
        String::new(),
        "theorem sourceSolveConfig_uses_initialize_kkt_default".to_string(),
        "    (initialize_config : SourceInitializeConfig) :".to_string(),
        "    (sourceSolveConfig initialize_config).kktSolve = initialize_config.kktDefaultSolveConfig := by".to_string(),
        "  rfl".to_string(),
        String::new(),
        "theorem sourceMain_is_algorithm_run".to_string(),
        "    (problem : SourceProblem)".to_string(),
        "    (initialize_config : SourceInitializeConfig) :".to_string(),
        "    sourceMain problem initialize_config =".to_string(),
        "      let initialized := sourceInitialize initialize_config".to_string(),
        "      initialized.1.run problem initialized.2 (sourceSolveConfig initialize_config) := by".to_string(),
        "  rfl".to_string(),
    ]);
    lines
}

fn render_source_return_structures(
    public_interface: Option<&serde_json::Map<String, Value>>,
) -> Vec<String> {
    let leaves = public_interface
        .and_then(|object| object.get("return_leaves"))
        .and_then(Value::as_array);
    let mut lines = Vec::new();
    for (root_name, structure_name) in [
        ("answer", "SourceAnswer"),
        ("state", "SourceState"),
        ("info", "SourceInfo"),
    ] {
        lines.push(format!("structure {structure_name} where"));
        let mut field_count = 0usize;
        if let Some(leaves) = leaves {
            for leaf in leaves {
                if value_field(leaf, "root_name") != root_name {
                    continue;
                }
                field_count += 1;
                lines.push(format!(
                    "  {} : {}",
                    source_field_name(value_field(leaf, "local_path")),
                    source_leaf_type(leaf),
                ));
            }
        }
        if field_count == 0 {
            lines.push("  unit : Unit".to_string());
        }
        lines.push(String::new());
    }
    lines
}

fn source_leaf_type(leaf: &Value) -> &'static str {
    let local_path = value_field(leaf, "local_path");
    if local_path == ".step_count" || local_path.ends_with(".step_count") {
        return "Nat";
    }
    let dtype = value_field(leaf, "dtype");
    let shape = value_field(leaf, "shape");
    if dtype.starts_with("int") || dtype.starts_with("uint") {
        "SourceInt"
    } else if shape == "()" {
        "SourceFloat"
    } else {
        "SourceVector"
    }
}

fn source_field_name(local_path: &str) -> String {
    let raw = local_path.trim_start_matches('.');
    let mut output = String::new();
    let mut uppercase_next = false;
    for ch in raw.chars() {
        if ch.is_ascii_alphanumeric() {
            if output.is_empty() && ch.is_ascii_digit() {
                output.push('f');
            }
            if uppercase_next {
                output.push(ch.to_ascii_uppercase());
            } else {
                output.push(ch);
            }
            uppercase_next = false;
        } else {
            uppercase_next = true;
        }
    }
    if output.is_empty() {
        "value".to_string()
    } else {
        output
    }
}

fn lean_string(value: impl AsRef<str>) -> String {
    let escaped = value
        .as_ref()
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n");
    format!("\"{escaped}\"")
}

fn render_string_list(values: &[Value], indent: &str) -> String {
    let items: Vec<String> = values
        .iter()
        .filter_map(Value::as_str)
        .map(lean_string)
        .collect();
    format!("{indent}[{}]", items.join(", "))
}

fn render_inline_string_list(values: Option<&Vec<Value>>) -> String {
    let Some(values) = values else {
        return "[]".to_string();
    };
    let items: Vec<String> = values
        .iter()
        .filter_map(Value::as_str)
        .map(lean_string)
        .collect();
    format!("[{}]", items.join(", "))
}

fn render_multiline_list(
    values: Option<&Vec<Value>>,
    mut render_item: impl FnMut(usize, &Value) -> String,
) -> String {
    const LEAN_LIST_CHUNK_SIZE: usize = 16;

    let Some(values) = values else {
        return "  []".to_string();
    };
    if values.is_empty() {
        return "  []".to_string();
    }
    if values.len() > LEAN_LIST_CHUNK_SIZE {
        let mut lines = vec!["  [".to_string()];
        for (chunk_index, chunk) in values.chunks(LEAN_LIST_CHUNK_SIZE).enumerate() {
            let chunk_comma = if (chunk_index + 1) * LEAN_LIST_CHUNK_SIZE >= values.len() {
                ""
            } else {
                ","
            };
            lines.push("    [".to_string());
            for (offset, value) in chunk.iter().enumerate() {
                let index = chunk_index * LEAN_LIST_CHUNK_SIZE + offset;
                let comma = if offset + 1 == chunk.len() { "" } else { "," };
                lines.push(format!("      {}{}", render_item(index, value), comma));
            }
            lines.push(format!("    ]{}", chunk_comma));
        }
        lines.push("  ].flatten".to_string());
        return lines.join("\n");
    }
    let mut lines = vec!["  [".to_string()];
    for (index, value) in values.iter().enumerate() {
        let comma = if index + 1 == values.len() { "" } else { "," };
        lines.push(format!("    {}{}", render_item(index, value), comma));
    }
    lines.push("  ]".to_string());
    lines.join("\n")
}

fn render_operational_functions(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, function| {
        let line_start = function
            .get("line_start")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let line_end = function
            .get("line_end")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        format!(
            "{{ functionId := {}, name := {}, signature := {}, lineStart := {}, lineEnd := {}, bodyRegionId := {} }}",
            lean_string(value_field(function, "function_id")),
            lean_string(value_field(function, "name")),
            lean_string(value_field(function, "signature")),
            line_start,
            line_end,
            lean_string(value_field(function, "body_region_id"))
        )
    })
}

fn render_operational_regions(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, region| {
        let depth = region.get("depth").and_then(Value::as_u64).unwrap_or(0);
        let line_start = region
            .get("line_start")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let line_end = region.get("line_end").and_then(Value::as_u64).unwrap_or(0);
        format!(
            "{{ regionId := {}, kind := {}, parentFunction := {}, parentOpId := {}, depth := {}, lineStart := {}, lineEnd := {}, opIds := {} }}",
            lean_string(value_field(region, "region_id")),
            lean_string(value_field(region, "kind")),
            lean_string(value_field(region, "parent_function")),
            lean_string(value_field(region, "parent_op_id")),
            depth,
            line_start,
            line_end,
            render_inline_string_list(region.get("op_ids").and_then(Value::as_array))
        )
    })
}

fn render_expansion_edges(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, edge| {
        format!(
            "{{ edgeId := {}, kind := {}, fromId := {}, toId := {} }}",
            lean_string(value_field(edge, "edge_id")),
            lean_string(value_field(edge, "kind")),
            lean_string(value_field(edge, "from")),
            lean_string(value_field(edge, "to"))
        )
    })
}

fn render_operational_coverage(coverage: Option<&serde_json::Map<String, Value>>) -> String {
    let field = |key: &str| -> u64 {
        coverage
            .and_then(|value| value.get(key))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    };
    let unresolved = coverage
        .and_then(|value| value.get("unresolved_call_targets"))
        .and_then(Value::as_array);
    format!(
        "  {{ functionCount := {}, regionCount := {}, expansionEdgeCount := {}, opCount := {}, unassignedOpCount := {}, maxRegionDepth := {}, whileCount := {}, caseCount := {}, ifCount := {}, callCount := {}, unresolvedCallTargets := {} }}",
        field("function_count"),
        field("region_count"),
        field("expansion_edge_count"),
        field("op_count"),
        field("unassigned_op_count"),
        field("max_region_depth"),
        field("while_count"),
        field("case_count"),
        field("if_count"),
        field("call_count"),
        render_inline_string_list(unresolved)
    )
}

fn nested_array<'a>(
    value: Option<&'a serde_json::Map<String, Value>>,
    path: &[&str],
) -> Option<&'a Vec<Value>> {
    let mut current = value?;
    for (index, key) in path.iter().enumerate() {
        let item = current.get(*key)?;
        if index + 1 == path.len() {
            return item.as_array();
        }
        current = item.as_object()?;
    }
    None
}

fn nested_object<'a>(
    value: Option<&'a serde_json::Map<String, Value>>,
    path: &[&str],
) -> Option<&'a serde_json::Map<String, Value>> {
    let mut current = value?;
    for key in path {
        current = current.get(*key)?.as_object()?;
    }
    Some(current)
}

fn render_inline_nat_list(values: Option<&Vec<Value>>) -> String {
    let Some(values) = values else {
        return "[]".to_string();
    };
    let items: Vec<String> = values
        .iter()
        .filter_map(Value::as_u64)
        .map(|value| value.to_string())
        .collect();
    format!("[{}]", items.join(", "))
}

fn value_nat_field(value: &Value, key: &str) -> u64 {
    value.get(key).and_then(Value::as_u64).unwrap_or(0)
}

fn value_bool_field(value: &serde_json::Map<String, Value>, key: &str) -> bool {
    value.get(key).and_then(Value::as_bool).unwrap_or(false)
}

fn render_public_roots(
    public_interface: Option<&serde_json::Map<String, Value>>,
    key: &str,
    label_key: &str,
) -> String {
    let roots = public_interface
        .and_then(|object| object.get(key))
        .and_then(Value::as_array);
    render_multiline_list(roots, |_index, root| {
        let label = value_field(root, label_key);
        let path = if value_field(root, "path").is_empty() {
            label
        } else {
            value_field(root, "path")
        };
        format!(
            "{{ index := {}, label := {}, annotation := {}, path := {} }}",
            value_nat_field(root, "index"),
            lean_string(label),
            lean_string(value_field(root, "annotation")),
            lean_string(path),
        )
    })
}

fn render_public_leaves(
    public_interface: Option<&serde_json::Map<String, Value>>,
    key: &str,
) -> String {
    let leaves = public_interface
        .and_then(|object| object.get(key))
        .and_then(Value::as_array);
    render_multiline_list(leaves, |_index, leaf| {
        format!(
            "{{ leafIndex := {}, rootIndex := {}, rootName := {}, path := {}, localPath := {}, pythonType := {}, shape := {}, dtype := {} }}",
            value_nat_field(leaf, "leaf_index"),
            value_nat_field(leaf, "root_index"),
            lean_string(value_field(leaf, "root_name")),
            lean_string(value_field(leaf, "path")),
            lean_string(value_field(leaf, "local_path")),
            lean_string(value_field(leaf, "python_type")),
            lean_string(value_field(leaf, "shape")),
            lean_string(value_field(leaf, "dtype")),
        )
    })
}

fn render_stablehlo_public_leaves(
    public_interface: Option<&serde_json::Map<String, Value>>,
    path: &[&str],
    has_result_info: bool,
) -> String {
    let leaves = nested_array(public_interface, path);
    render_multiline_list(leaves, |index, leaf| {
        let leaf_index = leaf
            .get("leaf_index")
            .and_then(Value::as_u64)
            .or_else(|| leaf.get("index").and_then(Value::as_u64))
            .unwrap_or(index as u64);
        let name = if has_result_info {
            format!("result{index}")
        } else {
            value_field(leaf, "name").to_string()
        };
        format!(
            "{{ leafIndex := {}, name := {}, stablehloType := {}, resultInfo := {}, resultIndexes := {} }}",
            leaf_index,
            lean_string(name),
            lean_string(value_field(leaf, "stablehlo_type")),
            lean_string(value_field(leaf, "result_info")),
            render_inline_nat_list(leaf.get("result_indexes").and_then(Value::as_array)),
        )
    })
}

fn render_public_interface_coverage(
    public_interface: Option<&serde_json::Map<String, Value>>,
) -> String {
    let coverage = nested_object(public_interface, &["coverage"]);
    let empty = serde_json::Map::new();
    let coverage = coverage.unwrap_or(&empty);
    format!(
        "  {{ argumentRootCount := {}, argumentLeafCount := {}, returnRootCount := {}, returnLeafCount := {}, stablehloArgumentCount := {}, stablehloReturnLeafCount := {}, hasAnswerStateInfoReturn := {} }}",
        coverage.get("argument_root_count").and_then(Value::as_u64).unwrap_or(0),
        coverage.get("argument_leaf_count").and_then(Value::as_u64).unwrap_or(0),
        coverage.get("return_root_count").and_then(Value::as_u64).unwrap_or(0),
        coverage.get("return_leaf_count").and_then(Value::as_u64).unwrap_or(0),
        coverage.get("stablehlo_argument_count").and_then(Value::as_u64).unwrap_or(0),
        coverage.get("stablehlo_return_leaf_count").and_then(Value::as_u64).unwrap_or(0),
        value_bool_field(coverage, "has_answer_state_info_return"),
    )
}

fn render_public_root_labels(public_interface: Option<&serde_json::Map<String, Value>>) -> String {
    let labels: Vec<Value> = public_interface
        .and_then(|object| object.get("return_roots"))
        .and_then(Value::as_array)
        .map(|roots| {
            roots
                .iter()
                .map(|root| Value::String(value_field(root, "label").to_string()))
                .collect()
        })
        .unwrap_or_default();
    render_inline_string_list(Some(&labels))
}

fn render_public_leaf_paths(public_interface: Option<&serde_json::Map<String, Value>>) -> String {
    let paths: Vec<Value> = public_interface
        .and_then(|object| object.get("return_leaves"))
        .and_then(Value::as_array)
        .map(|leaves| {
            leaves
                .iter()
                .map(|leaf| Value::String(value_field(leaf, "path").to_string()))
                .collect()
        })
        .unwrap_or_default();
    render_inline_string_list(Some(&paths))
}

fn render_operational_evaluator() -> Vec<String> {
    vec![
        "/-- Symbolic value carried by the generated operational evaluator. -/".to_string(),
        "structure OperationalValue where".to_string(),
        "  text : String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalBinding where".to_string(),
        "  name : String".to_string(),
        "  value : OperationalValue".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalFrame where".to_string(),
        "  functionName : String".to_string(),
        "  regionId : String".to_string(),
        "  remainingOpIds : List String".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalRuntimeState where".to_string(),
        "  bindings : List OperationalBinding".to_string(),
        "  frames : List OperationalFrame".to_string(),
        "  executedOpIds : List String".to_string(),
        "  missingOpIds : List String".to_string(),
        "  missingFunctionNames : List String".to_string(),
        "  missingRegionIds : List String".to_string(),
        "  fuelExhausted : Bool".to_string(),
        "deriving Repr, DecidableEq".to_string(),
        String::new(),
        "structure OperationalPrimitiveSemantics where".to_string(),
        "  evalPrimitive : OperationalOp -> OperationalRuntimeState -> OperationalRuntimeState".to_string(),
        "  selectWhileBody : OperationalOp -> OperationalRuntimeState -> Bool".to_string(),
        "  selectCaseBranch : OperationalOp -> OperationalRuntimeState -> Nat".to_string(),
        String::new(),
        "def emptyOperationalRuntimeState : OperationalRuntimeState :=".to_string(),
        "  { bindings := [], frames := [], executedOpIds := [], missingOpIds := [], missingFunctionNames := [], missingRegionIds := [], fuelExhausted := false }".to_string(),
        String::new(),
        "def bindOperationalValue (name : String) (value : OperationalValue) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  { state with bindings := { name := name, value := value } :: state.bindings }".to_string(),
        String::new(),
        "def symbolicOperationalPrimitiveSemantics : OperationalPrimitiveSemantics :=".to_string(),
        "  { evalPrimitive := fun op state => bindOperationalValue op.opId { text := op.textSha256 } state".to_string(),
        "    selectWhileBody := fun _op _state => false".to_string(),
        "    selectCaseBranch := fun _op _state => 0 }".to_string(),
        String::new(),
        "noncomputable def findOperationalOp (opId : String) : Option OperationalOp :=".to_string(),
        "  operationalOps.find? (fun op => op.opId == opId)".to_string(),
        String::new(),
        "def findOperationalFunction (functionName : String) : Option OperationalFunction :=".to_string(),
        "  operationalFunctions.find? (fun fn => fn.name == functionName)".to_string(),
        String::new(),
        "def findOperationalRegion (regionId : String) : Option OperationalRegion :=".to_string(),
        "  operationalRegions.find? (fun region => region.regionId == regionId)".to_string(),
        String::new(),
        "def expansionTargets (kind fromId : String) : List String :=".to_string(),
        "  (expansionEdges.filter (fun edge => edge.kind == kind && edge.fromId == fromId)).map (fun edge => edge.toId)".to_string(),
        String::new(),
        "def firstExpansionTarget (kind fromId : String) : Option String :=".to_string(),
        "  (expansionTargets kind fromId).head?".to_string(),
        String::new(),
        "def listGetAt? {α : Type} : List α -> Nat -> Option α".to_string(),
        "  | [], _ => none".to_string(),
        "  | value :: _rest, 0 => some value".to_string(),
        "  | _value :: rest, index + 1 => listGetAt? rest index".to_string(),
        String::new(),
        "def functionBodyRegionId (functionName : String) : Option String :=".to_string(),
        "  match findOperationalFunction functionName with".to_string(),
        "  | some fn => some fn.bodyRegionId".to_string(),
        "  | none => none".to_string(),
        String::new(),
        "def frameForRegion (functionName regionId : String) : Option OperationalFrame :=".to_string(),
        "  match findOperationalRegion regionId with".to_string(),
        "  | some region => some { functionName := functionName, regionId := regionId, remainingOpIds := region.opIds }".to_string(),
        "  | none => none".to_string(),
        String::new(),
        "def pushFrame (frame : OperationalFrame) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  { state with frames := frame :: state.frames }".to_string(),
        String::new(),
        "def popFrame (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match state.frames with".to_string(),
        "  | [] => state".to_string(),
        "  | _frame :: rest => { state with frames := rest }".to_string(),
        String::new(),
        "def pushRegionFrame (functionName regionId : String) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match frameForRegion functionName regionId with".to_string(),
        "  | some frame => pushFrame frame state".to_string(),
        "  | none => { state with missingRegionIds := regionId :: state.missingRegionIds }".to_string(),
        String::new(),
        "def pushFunctionFrame (functionName : String) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match functionBodyRegionId functionName with".to_string(),
        "  | some regionId => pushRegionFrame functionName regionId state".to_string(),
        "  | none => { state with missingFunctionNames := functionName :: state.missingFunctionNames }".to_string(),
        String::new(),
        "def recordExecutedOp (op : OperationalOp) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  { state with executedOpIds := state.executedOpIds ++ [op.opId] }".to_string(),
        String::new(),
        "def executeWhileOp (semantics : OperationalPrimitiveSemantics) (op : OperationalOp) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match firstExpansionTarget \"while_cond\" op.opId, firstExpansionTarget \"while_do\" op.opId with".to_string(),
        "  | some condRegionId, some bodyRegionId =>".to_string(),
        "      let withBody := if semantics.selectWhileBody op state then pushRegionFrame op.functionName bodyRegionId state else state".to_string(),
        "      pushRegionFrame op.functionName condRegionId withBody".to_string(),
        "  | none, some bodyRegionId =>".to_string(),
        "      { state with missingRegionIds := (\"while_cond:\" ++ op.opId) :: bodyRegionId :: state.missingRegionIds }".to_string(),
        "  | some condRegionId, none =>".to_string(),
        "      { state with missingRegionIds := condRegionId :: (\"while_do:\" ++ op.opId) :: state.missingRegionIds }".to_string(),
        "  | none, none =>".to_string(),
        "      { state with missingRegionIds := (\"while_cond:\" ++ op.opId) :: (\"while_do:\" ++ op.opId) :: state.missingRegionIds }".to_string(),
        String::new(),
        "def executeCaseOp (semantics : OperationalPrimitiveSemantics) (op : OperationalOp) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match listGetAt? (expansionTargets \"case_branch\" op.opId) (semantics.selectCaseBranch op state) with".to_string(),
        "  | some regionId => pushRegionFrame op.functionName regionId state".to_string(),
        "  | none => { state with missingRegionIds := (\"case_branch:\" ++ op.opId) :: state.missingRegionIds }".to_string(),
        String::new(),
        "def executeOperationalOp (semantics : OperationalPrimitiveSemantics) (op : OperationalOp) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  let tracedState := recordExecutedOp op state".to_string(),
        "  if op.kind == \"Call\" then".to_string(),
        "    if op.callTarget == \"\" then semantics.evalPrimitive op tracedState else pushFunctionFrame op.callTarget tracedState".to_string(),
        "  else if op.kind == \"While\" then".to_string(),
        "    executeWhileOp semantics op tracedState".to_string(),
        "  else if op.kind == \"Case\" then".to_string(),
        "    executeCaseOp semantics op tracedState".to_string(),
        "  else if op.kind == \"Return\" then".to_string(),
        "    popFrame tracedState".to_string(),
        "  else if op.kind == \"Primitive\" then".to_string(),
        "    semantics.evalPrimitive op tracedState".to_string(),
        "  else".to_string(),
        "    tracedState".to_string(),
        String::new(),
        "noncomputable def stepOperational (semantics : OperationalPrimitiveSemantics) (state : OperationalRuntimeState) : OperationalRuntimeState :=".to_string(),
        "  match state.frames with".to_string(),
        "  | [] => state".to_string(),
        "  | frame :: rest =>".to_string(),
        "      match frame.remainingOpIds with".to_string(),
        "      | [] => { state with frames := rest }".to_string(),
        "      | opId :: remaining =>".to_string(),
        "          let advancedState := { state with frames := { frame with remainingOpIds := remaining } :: rest }".to_string(),
        "          match findOperationalOp opId with".to_string(),
        "          | some op => executeOperationalOp semantics op advancedState".to_string(),
        "          | none => { advancedState with missingOpIds := opId :: advancedState.missingOpIds }".to_string(),
        String::new(),
        "noncomputable def runOperationalFuel (semantics : OperationalPrimitiveSemantics) : Nat -> OperationalRuntimeState -> OperationalRuntimeState".to_string(),
        "  | 0, state => { state with fuelExhausted := state.frames != [] }".to_string(),
        "  | fuel + 1, state =>".to_string(),
        "      if state.frames == [] then state else runOperationalFuel semantics fuel (stepOperational semantics state)".to_string(),
        String::new(),
        "noncomputable def generatedMainInitialState : OperationalRuntimeState :=".to_string(),
        "  pushFunctionFrame operationalProgram.entryFunction emptyOperationalRuntimeState".to_string(),
        String::new(),
        "noncomputable def generatedMainFuel (semantics : OperationalPrimitiveSemantics) (fuel : Nat) : OperationalRuntimeState :=".to_string(),
        "  runOperationalFuel semantics fuel generatedMainInitialState".to_string(),
        String::new(),
        "noncomputable def generatedMainSymbolicFuel (fuel : Nat) : OperationalRuntimeState :=".to_string(),
        "  generatedMainFuel symbolicOperationalPrimitiveSemantics fuel".to_string(),
        String::new(),
        "theorem generatedMainFuel_zero (semantics : OperationalPrimitiveSemantics) :".to_string(),
        "    generatedMainFuel semantics 0 = { generatedMainInitialState with fuelExhausted := generatedMainInitialState.frames != [] } := by".to_string(),
        "  rfl".to_string(),
        String::new(),
    ]
}

fn render_count_map(values: Option<&serde_json::Map<String, Value>>) -> String {
    let Some(values) = values else {
        return "[]".to_string();
    };
    let items: Vec<String> = values
        .iter()
        .filter_map(|(key, value)| value.as_u64().map(|count| (key, count)))
        .map(|(key, count)| format!("{{ key := {}, count := {} }}", lean_string(key), count))
        .collect();
    format!("[{}]", items.join(", "))
}

fn render_llvm_basic_blocks(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, block| {
        let line = block.get("line").and_then(Value::as_u64).unwrap_or(0);
        format!(
            "({{ label := {}, line := {}, instructionIds := {} }} : LlvmBasicBlockTrace)",
            lean_string(value_field(block, "label")),
            line,
            render_inline_string_list(block.get("instruction_ids").and_then(Value::as_array))
        )
    })
}

fn render_llvm_instructions(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, instruction| {
        let line = instruction.get("line").and_then(Value::as_u64).unwrap_or(0);
        let is_float = instruction
            .get("is_float_op")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        format!(
            "({{ instructionId := {}, functionName := {}, basicBlock := {}, line := {}, resultName := {}, opcode := {}, operandText := {}, text := {}, textSha256 := {}, fastMathFlags := {}, isFloatOp := {} }} : LlvmInstructionTrace)",
            lean_string(value_field(instruction, "instruction_id")),
            lean_string(value_field(instruction, "function")),
            lean_string(value_field(instruction, "basic_block")),
            line,
            lean_string(value_field(instruction, "result_name")),
            lean_string(value_field(instruction, "opcode")),
            lean_string(value_field(instruction, "operand_text")),
            lean_string(value_field(instruction, "text")),
            lean_string(value_field(instruction, "text_sha256")),
            render_inline_string_list(instruction.get("fast_math_flags").and_then(Value::as_array)),
            is_float
        )
    })
}

fn collect_llvm_instructions(values: Option<&Vec<Value>>) -> Vec<Value> {
    let mut instructions = Vec::new();
    let Some(modules) = values else {
        return instructions;
    };
    for module in modules {
        let Some(functions) = module.get("functions").and_then(Value::as_array) else {
            continue;
        };
        for function in functions {
            let Some(items) = function.get("instructions").and_then(Value::as_array) else {
                continue;
            };
            instructions.extend(items.iter().cloned());
        }
    }
    instructions
}

fn collect_llvm_basic_blocks(values: Option<&Vec<Value>>) -> Vec<Value> {
    let mut blocks = Vec::new();
    let Some(modules) = values else {
        return blocks;
    };
    for module in modules {
        let Some(functions) = module.get("functions").and_then(Value::as_array) else {
            continue;
        };
        for function in functions {
            let Some(items) = function.get("basic_blocks").and_then(Value::as_array) else {
                continue;
            };
            blocks.extend(items.iter().cloned());
        }
    }
    blocks
}

fn llvm_basic_block_labels(values: Option<&Vec<Value>>) -> Vec<Value> {
    let Some(values) = values else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|block| {
            block
                .get("label")
                .and_then(Value::as_str)
                .map(|value| Value::String(value.to_string()))
        })
        .collect()
}

fn llvm_instruction_ids(values: Option<&Vec<Value>>) -> Vec<Value> {
    let Some(values) = values else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|instruction| {
            instruction
                .get("instruction_id")
                .and_then(Value::as_str)
                .map(|value| Value::String(value.to_string()))
        })
        .collect()
}

fn render_llvm_functions(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, function| {
        let basic_blocks = function.get("basic_blocks").and_then(Value::as_array);
        let basic_block_labels = llvm_basic_block_labels(basic_blocks);
        let instructions = function.get("instructions").and_then(Value::as_array);
        let instruction_ids = llvm_instruction_ids(instructions);
        let instruction_count = function
            .get("instruction_count")
            .and_then(Value::as_u64)
            .unwrap_or_else(|| instructions.map_or(0, |items| items.len() as u64));
        let float_instruction_count = function
            .get("float_instruction_count")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        format!(
            "({{ name := {}, signature := {}, returnAndAttrs := {}, params := {}, opCounts := {}, fastMathFlags := {}, basicBlockLabels := {}, instructionIds := {}, instructionCount := {}, floatInstructionCount := {} }} : LlvmFunctionTrace)",
            lean_string(value_field(function, "name")),
            lean_string(value_field(function, "signature")),
            lean_string(value_field(function, "return_and_attrs")),
            lean_string(value_field(function, "params")),
            render_count_map(function.get("op_counts").and_then(Value::as_object)),
            render_count_map(function.get("fast_math_flags").and_then(Value::as_object)),
            render_inline_string_list(Some(&basic_block_labels)),
            render_inline_string_list(Some(&instruction_ids)),
            instruction_count,
            float_instruction_count
        )
    })
}

fn render_llvm_modules(values: Option<&Vec<Value>>) -> String {
    render_multiline_list(values, |_index, module| {
        let functions = module.get("functions").and_then(Value::as_array);
        let function_count = functions.map_or(0, |items| items.len());
        let basic_block_count = module
            .get("basic_block_count")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let instruction_count = module
            .get("instruction_count")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let float_instruction_count = module
            .get("float_instruction_count")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let rendered_functions = render_llvm_functions(functions);
        let rendered_functions = rendered_functions.trim_start();
        format!(
            "({{ path := {}, sha256 := {}, kind := {}, functionCount := {}, basicBlockCount := {}, instructionCount := {}, floatInstructionCount := {}, opCounts := {}, fastMathFlags := {}, functions := {} }} : LlvmModuleTrace)",
            lean_string(value_field(module, "path")),
            lean_string(value_field(module, "sha256")),
            lean_string(value_field(module, "kind")),
            function_count,
            basic_block_count,
            instruction_count,
            float_instruction_count,
            render_count_map(module.get("op_counts").and_then(Value::as_object)),
            render_count_map(module.get("fast_math_flags").and_then(Value::as_object)),
            rendered_functions
        )
    })
}

fn entry_function_name(values: Option<&Vec<Value>>) -> String {
    values
        .and_then(|items| items.first())
        .map(|value| value_field(value, "name").to_string())
        .unwrap_or_default()
}

fn sanitize_namespace(value: &str) -> String {
    let mut output = String::new();
    let mut uppercase_next = true;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() {
            if output.is_empty() && ch.is_ascii_digit() {
                output.push('N');
            }
            if uppercase_next {
                output.push(ch.to_ascii_uppercase());
            } else {
                output.push(ch);
            }
            uppercase_next = false;
        } else {
            uppercase_next = true;
        }
    }
    if output.is_empty() {
        "GeneratedJit".to_string()
    } else {
        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample_public_interface() -> Value {
        json!({
            "schema": "agent-canon.public-interface.v1",
            "python_symbol": "root.py::main",
            "source_signature": {
                "return_annotation": "tuple[Answer, State, Info]"
            },
            "argument_roots": [
                {"index": 0, "name": "problem", "annotation": "Problem"},
                {"index": 1, "name": "initialize_config", "annotation": "InitializeConfig"}
            ],
            "argument_leaves": [
                {
                    "leaf_index": 0,
                    "root_index": 0,
                    "root_name": "problem",
                    "path": "problem.x0",
                    "local_path": ".x0",
                    "python_type": "Array",
                    "shape": "(2,)",
                    "dtype": "float32"
                }
            ],
            "return_annotation": "tuple[Answer, State, Info]",
            "return_roots": [
                {"index": 0, "label": "answer", "annotation": "Answer", "path": "result[0]"},
                {"index": 1, "label": "state", "annotation": "State", "path": "result[1]"},
                {"index": 2, "label": "info", "annotation": "Info", "path": "result[2]"}
            ],
            "return_leaves": [
                {
                    "leaf_index": 0,
                    "root_index": 0,
                    "root_name": "answer",
                    "path": "answer.objective_value",
                    "local_path": ".objective_value",
                    "python_type": "Array",
                    "shape": "()",
                    "dtype": "float32"
                },
                {
                    "leaf_index": 1,
                    "root_index": 0,
                    "root_name": "answer",
                    "path": "answer.status",
                    "local_path": ".status",
                    "python_type": "Array",
                    "shape": "()",
                    "dtype": "int32"
                },
                {
                    "leaf_index": 0,
                    "root_index": 1,
                    "root_name": "state",
                    "path": "state.x",
                    "local_path": ".x",
                    "python_type": "Array",
                    "shape": "(2,)",
                    "dtype": "float32"
                },
                {
                    "leaf_index": 0,
                    "root_index": 2,
                    "root_name": "info",
                    "path": "info.step_count",
                    "local_path": ".step_count",
                    "python_type": "Array",
                    "shape": "()",
                    "dtype": "int32"
                },
                {
                    "leaf_index": 1,
                    "root_index": 2,
                    "root_name": "info",
                    "path": "info.ipm_res_final",
                    "local_path": ".ipm_res_final",
                    "python_type": "Array",
                    "shape": "()",
                    "dtype": "float32"
                }
            ],
            "stablehlo_entry": {
                "signature": "func.func public @main(%arg0: tensor<2xf32>) -> (tensor<f32> {jax.result_info = \"result[0].objective_value\"})",
                "arguments": [
                    {"index": 0, "name": "arg0", "stablehlo_type": "tensor<2xf32>"}
                ],
                "return_leaves": [
                    {
                        "leaf_index": 0,
                        "result_info": "result[0].objective_value",
                        "stablehlo_type": "tensor<f32>",
                        "result_indexes": [0]
                    }
                ]
            },
            "coverage": {
                "argument_root_count": 2,
                "argument_leaf_count": 1,
                "return_root_count": 3,
                "return_leaf_count": 5,
                "stablehlo_argument_count": 1,
                "stablehlo_return_leaf_count": 1,
                "has_answer_state_info_return": true
            }
        })
    }

    #[test]
    fn render_lean_expands_llvm_modules_and_functions() {
        let args = Args {
            jit_ir: PathBuf::from("root.json"),
            namespace: "Smoke".to_string(),
            module_name: "sample".to_string(),
            out: PathBuf::from("Generated.lean"),
        };
        let value = json!({
            "root": {
                "python_symbol": "root.py::main",
                "input_factory_symbol": "root.py::inputs"
            },
            "stablehlo": {
                "sha256": "stablehlo-digest",
                "dialect": "stablehlo"
            },
            "source_root": {
                "schema": "agent-canon.source-root.v1",
                "python_symbol": "root.py::main",
                "path": "/workspace/root.py",
                "qualname": "main",
                "name": "main",
                "parameters": ["problem", "initialize_config"],
                "return_annotation": "tuple[Answer, State, Info]",
                "source_sha256": "source-digest",
                "main_pattern": {
                    "pattern": "initialize_then_algorithm_call_return_tuple",
                    "initialize": {
                        "assigned": ["algorithm", "state"],
                        "callee": "pdipm.initialize",
                        "args": ["initialize_config"]
                    },
                    "algorithm_call": {
                        "assigned": ["answer", "next_state", "info"],
                        "callee": "algorithm",
                        "args": [
                            "problem",
                            "state",
                            "pdipm.SolveConfig(kkt_solve=initialize_config.kkt_default_solve_config)"
                        ],
                        "solve_config": {
                            "constructor": "pdipm.SolveConfig",
                            "keywords": {
                                "kkt_solve": "initialize_config.kkt_default_solve_config"
                            },
                            "stopping_constructor": "stopping.SolveConfig",
                            "stopping_keywords": {
                                "maxiter": 1,
                                "rtol": "1e-4",
                                "atol": "0.0",
                                "reference": "rhs",
                                "norm": "linf",
                                "squared": 0,
                                "runtime_rtol": "configured",
                                "runtime_atol": "configured"
                            }
                        }
                    },
                    "return": ["answer", "next_state", "info"]
                }
            },
            "public_interface": sample_public_interface(),
            "operational_ir": {
                "allowed_kinds": ["Function", "Primitive", "Return"],
                "ops": [
                    {
                        "op_id": "op_00000",
                        "kind": "Function",
                        "opcode": "func.func",
                        "line": 1,
                        "text_sha256": "op-digest",
                        "dtypes": ["f32"],
                        "function": "main",
                        "region_id": "region_00000",
                        "parent_op_id": "",
                        "call_target": ""
                    }
                ],
                "functions": [
                    {
                        "function_id": "function:main",
                        "name": "main",
                        "signature": "func.func @main()",
                        "line_start": 1,
                        "line_end": 3,
                        "body_region_id": "region_00001"
                    }
                ],
                "regions": [
                    {
                        "region_id": "region_00000",
                        "kind": "module",
                        "parent_function": "",
                        "parent_op_id": "",
                        "depth": 0,
                        "line_start": 1,
                        "line_end": 3,
                        "op_ids": ["op_00000"]
                    }
                ],
                "expansion_edges": [
                    {
                        "edge_id": "edge_00000",
                        "kind": "program_root",
                        "from": "program",
                        "to": "region_00000"
                    }
                ],
                "coverage": {
                    "function_count": 1,
                    "region_count": 1,
                    "expansion_edge_count": 1,
                    "op_count": 1,
                    "unassigned_op_count": 0,
                    "max_region_depth": 0,
                    "while_count": 0,
                    "case_count": 0,
                    "if_count": 0,
                    "call_count": 0,
                    "unresolved_call_targets": []
                }
            },
            "backend_trace": {
                "coverage": "generated_with_llvm",
                "target_backend": "llvm-cpu",
                "executables": {
                    "iree-compile": "/usr/bin/iree-compile",
                    "iree-run-module": null
                },
                "last_successful_phase": "vm",
                "phase_traces": [],
                "compile_attempts": [],
                "executable_sources": [],
                "llvm_bitcode": [],
                "llvm_ir": [
                    {
                        "path": "backend/module.ll",
                        "sha256": "llvm-digest",
                        "kind": "llvm_ir",
                        "basic_block_count": 1,
                        "instruction_count": 2,
                        "float_instruction_count": 2,
                        "op_counts": {"fadd": 2, "fmul": 1},
                        "fast_math_flags": {"contract": 1},
                        "functions": [
                            {
                                "name": "main_dispatch",
                                "signature": "define float @main_dispatch(float %x)",
                                "return_and_attrs": "float",
                                "params": "float %x",
                                "op_counts": {"fadd": 2},
                                "fast_math_flags": {"contract": 1},
                                "basic_blocks": [
                                    {
                                        "label": "entry",
                                        "line": 1,
                                        "instruction_ids": [
                                            "main_dispatch:inst_00000",
                                            "main_dispatch:inst_00001"
                                        ]
                                    }
                                ],
                                "instructions": [
                                    {
                                        "instruction_id": "main_dispatch:inst_00000",
                                        "function": "main_dispatch",
                                        "basic_block": "entry",
                                        "line": 2,
                                        "result_name": "%1",
                                        "opcode": "fmul",
                                        "operand_text": "contract float %x, %x",
                                        "text": "%1 = fmul contract float %x, %x",
                                        "text_sha256": "inst-digest-0",
                                        "fast_math_flags": ["contract"],
                                        "is_float_op": true
                                    },
                                    {
                                        "instruction_id": "main_dispatch:inst_00001",
                                        "function": "main_dispatch",
                                        "basic_block": "entry",
                                        "line": 3,
                                        "result_name": "%2",
                                        "opcode": "fadd",
                                        "operand_text": "contract float %1, 1.0",
                                        "text": "%2 = fadd contract float %1, 1.0",
                                        "text_sha256": "inst-digest-1",
                                        "fast_math_flags": ["contract"],
                                        "is_float_op": true
                                    }
                                ],
                                "instruction_count": 2,
                                "float_instruction_count": 2
                            }
                        ]
                    }
                ]
            }
        });

        let rendered = render_lean(&args, &value).expect("render Lean");
        assert!(rendered.contains("structure LlvmModuleTrace"));
        assert!(rendered.contains("structure LlvmBasicBlockTrace"));
        assert!(rendered.contains("structure LlvmInstructionTrace"));
        assert!(rendered.contains("def llvmModules : List LlvmModuleTrace"));
        assert!(rendered.contains("def llvmBasicBlocks : List LlvmBasicBlockTrace"));
        assert!(rendered.contains("def llvmInstructions : List LlvmInstructionTrace"));
        assert!(rendered.contains("structure LlvmRuntimeState"));
        assert!(rendered.contains("structure LlvmPrimitiveSemantics"));
        assert!(rendered.contains("structure OperationalRuntimeState"));
        assert!(rendered.contains("structure OperationalPrimitiveSemantics"));
        assert!(rendered.contains("def stepOperational"));
        assert!(rendered.contains("def runOperationalFuel"));
        assert!(rendered.contains("noncomputable def generatedMainFuel"));
        assert!(rendered.contains("structure SourceRoot"));
        assert!(rendered.contains("def sourceRoot : SourceRoot"));
        assert!(rendered.contains("structure SourceAnswer where"));
        assert!(rendered.contains("objectiveValue : SourceFloat"));
        assert!(rendered.contains("status : SourceInt"));
        assert!(rendered.contains("structure SourceState where"));
        assert!(rendered.contains("x : SourceVector"));
        assert!(rendered.contains("structure SourceInfo where"));
        assert!(rendered.contains("stepCount : Nat"));
        assert!(rendered.contains("ipmResFinal : SourceFloat"));
        assert!(rendered.contains("noncomputable def sourceMain"));
        assert!(rendered.contains("sourceSolveConfig initialize_config"));
        assert!(rendered.contains("def publicAnswerLeafPaths : List String"));
        assert!(rendered.contains("answer.objective_value"));
        assert!(rendered.contains("answer.status"));
        assert!(rendered.contains("hasAnswerStateInfoReturn := true"));
        assert!(rendered.contains("sourceMain_embeds_python_main"));
        assert!(rendered.contains("def executeLlvmInstruction"));
        assert!(rendered.contains("def runLlvmInstructions"));
        assert!(rendered.contains("def generatedLlvmRuntimeState"));
        assert!(rendered.contains("generated_llvm_runtime_records_all_instructions"));
        assert!(rendered.contains("main_dispatch"));
        assert!(rendered.contains("main_dispatch:inst_00000"));
        assert!(rendered.contains("fadd"));
        assert!(rendered.contains("generated_backend_llvm_count_matches"));
        assert!(rendered.contains("generated_backend_llvm_basic_block_count_matches"));
        assert!(rendered.contains("generated_backend_llvm_instruction_count_matches"));
        assert!(rendered.contains("llvmModuleCount := llvmModules.length"));
    }

    #[test]
    fn render_lean_omits_source_and_backend_routes_for_hlo_only_root() {
        let args = Args {
            jit_ir: PathBuf::from("root.json"),
            namespace: "Smoke".to_string(),
            module_name: "sample".to_string(),
            out: PathBuf::from("Generated.lean"),
        };
        let value = json!({
            "root": {
                "python_symbol": "root.py::main",
                "input_factory_symbol": "root.py::inputs"
            },
            "stablehlo": {
                "sha256": "stablehlo-digest",
                "dialect": "stablehlo"
            },
            "source_root": {
                "schema": "agent-canon.source-root.v1",
                "status": "hlo_only",
                "python_symbol": "root.py::main",
                "path": "/workspace/root.py",
                "qualname": "main",
                "name": "main",
                "parameters": [],
                "return_annotation": "",
                "source_sha256": "",
                "main_pattern": null
            },
            "public_interface": sample_public_interface(),
            "operational_ir": {
                "allowed_kinds": ["Function", "Primitive", "Return"],
                "ops": [],
                "functions": [],
                "regions": [],
                "expansion_edges": [],
                "coverage": {
                    "function_count": 0,
                    "region_count": 0,
                    "expansion_edge_count": 0,
                    "op_count": 0,
                    "unassigned_op_count": 0,
                    "max_region_depth": 0,
                    "while_count": 0,
                    "case_count": 0,
                    "if_count": 0,
                    "call_count": 0,
                    "unresolved_call_targets": []
                }
            }
        });

        let rendered = render_lean(&args, &value).expect("render Lean");
        assert!(!rendered.contains("structure SourceRoot"));
        assert!(!rendered.contains("def sourceRoot"));
        assert!(!rendered.contains("noncomputable def sourceMain"));
        assert!(!rendered.contains("BackendTrace"));
        assert!(!rendered.contains("Llvm"));
        assert!(!rendered.contains("llvm"));
        assert!(!rendered.contains("iree"));
        assert!(rendered.contains("structure OperationalRuntimeState"));
        assert!(rendered.contains("structure OperationalPrimitiveSemantics"));
        assert!(rendered.contains("def stepOperational"));
        assert!(rendered.contains("def runOperationalFuel"));
        assert!(rendered.contains("noncomputable def generatedMainFuel"));
        assert!(rendered.contains("stablehloSha256"));
        assert!(rendered.contains("generatedFunction_root"));
    }

    #[test]
    fn render_lean_rejects_missing_public_interface() {
        let args = Args {
            jit_ir: PathBuf::from("root.json"),
            namespace: "Smoke".to_string(),
            module_name: "sample".to_string(),
            out: PathBuf::from("Generated.lean"),
        };
        let value = json!({
            "root": {
                "python_symbol": "root.py::main",
                "input_factory_symbol": "root.py::inputs"
            },
            "stablehlo": {
                "sha256": "stablehlo-digest",
                "dialect": "stablehlo"
            },
            "operational_ir": {
                "allowed_kinds": ["Function"],
                "ops": [],
                "coverage": {}
            }
        });

        let error = render_lean(&args, &value).expect_err("public interface is required");
        assert!(error.contains("missing public_interface object"));
    }

    #[test]
    fn render_lean_rejects_malformed_public_interface_schema() {
        let args = Args {
            jit_ir: PathBuf::from("root.json"),
            namespace: "Smoke".to_string(),
            module_name: "sample".to_string(),
            out: PathBuf::from("Generated.lean"),
        };
        let mut public_interface = sample_public_interface();
        public_interface["schema"] = Value::String("wrong.schema".to_string());
        let value = json!({
            "root": {
                "python_symbol": "root.py::main",
                "input_factory_symbol": "root.py::inputs"
            },
            "stablehlo": {
                "sha256": "stablehlo-digest",
                "dialect": "stablehlo"
            },
            "public_interface": public_interface,
            "operational_ir": {
                "allowed_kinds": ["Function"],
                "ops": [],
                "coverage": {}
            }
        });

        let error = render_lean(&args, &value).expect_err("public schema is required");
        assert!(error.contains("expected public_interface.schema"));
    }

    #[test]
    fn render_lean_rejects_non_answer_state_info_public_return() {
        let args = Args {
            jit_ir: PathBuf::from("root.json"),
            namespace: "Smoke".to_string(),
            module_name: "sample".to_string(),
            out: PathBuf::from("Generated.lean"),
        };
        let mut public_interface = sample_public_interface();
        public_interface["coverage"]["has_answer_state_info_return"] = Value::Bool(false);
        let value = json!({
            "root": {
                "python_symbol": "root.py::main",
                "input_factory_symbol": "root.py::inputs"
            },
            "stablehlo": {
                "sha256": "stablehlo-digest",
                "dialect": "stablehlo"
            },
            "public_interface": public_interface,
            "operational_ir": {
                "allowed_kinds": ["Function"],
                "ops": [],
                "coverage": {}
            }
        });

        let error = render_lean(&args, &value).expect_err("Answer/State/Info return is required");
        assert!(error.contains("expected public_interface.coverage.has_answer_state_info_return"));
    }
}
