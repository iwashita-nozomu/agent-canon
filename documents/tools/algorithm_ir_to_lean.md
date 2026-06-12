<!--
@dependency-start
responsibility Documents algorithm-ir-to-lean operator usage.
upstream implementation ../../rust/agent-canon/src/algorithm_ir_to_lean.rs lowers Algorithm IR into Lean route artifacts.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds the consumed Algorithm IR.
upstream design ../design/algorithm-ir-to-lean.md defines the lowering architecture.
upstream design ../../agents/skills/formal-proof-workflow.md defines implementation-trace proof routing.
@dependency-end
-->

# algorithm-ir-to-lean

`agent-canon algorithm-ir-to-lean` converts Algorithm Expansion IR into a
generic Lean route module. Python owns AST extraction; Rust owns IR validation,
structure projection normalization, and Lean emission.

Use it after `algorithm_expansion_ir.py`:

```bash
tools/bin/agent-canon algorithm-ir-to-lean \
  --algorithm-ir lean/pdipm_convergence/pdipm_solve_ir.json \
  --namespace PDIPMConvergence.GeneratedPdipmSolve \
  --module-name pdipm_solve \
  --out lean/pdipm_convergence/PDIPMConvergence/GeneratedPdipmSolve.lean
```

The command requires `code_facts[*].expression_ast`. Expression strings are
human-readable metadata only and are not parsed for semantics.

## Output Contract

The generated Lean file contains:

- `Expr` for Python AST expression nodes;
- `ProjectionSegment` for post-IR structure access normalization;
- `CodeEquation` records for assignment and return equations;
- one named `fact_... : CodeEquation` Lean definition per generated code fact;
- `ControlFact` records for branch and loop facts;
- `SubstitutionRoute` definitions grouped by source symbol.

The generated Lean file must not contain:

- raw-expression escape constructors;
- `Env`, `Value`, `eval`, `bind`, or interpreter-style escape hatches;
- algorithm-specific typed models such as PDIPM `State` or `Direction`;
- theorem-specific assumptions or convergence certificates.

## Scope

This command preserves implementation route shape. It does not prove
convergence and does not decide which mathematical lemmas are sufficient.
Proof themes import the generated route module, then add theorem-specific
definitions and bridge lemmas in separate proof files.

When the Python algorithm changes, regenerate Algorithm IR and rerun this
command. Do not edit generated theorem content by hand.
