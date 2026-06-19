---
name: algorithm-flowchart
description: Use when rendering JIT-canonical IR records, generated Lean evidence modules, and theorem-graph proof overlays into Mermaid block charts that show the implemented iterative algorithm and proof state.
---

<!--
@dependency-start
contract skill
responsibility Exposes JIT-canonical algorithm Mermaid flowcharts to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/algorithm-flowchart.md canonical skill document
upstream design ../../../agents/skills/algorithm-proof-exploration.md JIT-canonical IR and theorem graph workflow.
upstream design ../../../agents/skills/formal-proof-workflow.md proof status workflow.
upstream implementation ../../../tools/agent_tools/jit_canonical_ir.py emits StableHLO-derived operational IR and backend traces.
upstream implementation ../../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR to Lean evidence modules.
@dependency-end
-->

# Algorithm Flowchart

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-flowchart --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/algorithm-flowchart.md`.
1. Use this with `$algorithm-proof-exploration` or `$formal-proof-workflow`
   when the task asks what iterative algorithm is implemented, where solver
   chain blocks are, or which blocks are verified/open/external.
1. Generate or reuse JIT-canonical IR first:
   `python3 tools/agent_tools/jit_canonical_ir.py --python-symbol <path.py::qualname> --input-factory <path.py::qualname> --out <ir.json> --stablehlo-out <root.stablehlo.mlir> --backend-trace-dir <dir> --backend-trace-out <backend.json>`.
1. Generate or reuse the Lean evidence module:
   `tools/bin/agent-canon jit-ir-to-lean --jit-ir <ir.json> --namespace <Namespace> --module-name <Name> --out <Generated.lean>`.
1. Render the chart mechanically from the current generated evidence
   layer and theorem-graph overlay. If the current renderer cannot consume the
   JIT-canonical record, update the renderer first instead of falling back to
   retired artifacts.
   Use implementation-only views for runtime flow and theorem-overlay views for
   proof-relevant mathematical / solver core without proof-only runtime labels
   or branches.
1. Do not hand-draw or manually maintain diagrams for implementation-derived
   algorithms. If code or proof overlays change, regenerate IR, graph, proof
   analyzer output, and flowchart in that order.
1. Do not hand-write theorem-critical equation prose when it can be generated
   from the current JIT-canonical record and theorem graph overlay. Missing
   equations are extractor or implementation-shape issues, not permission to
   revive retired artifacts.
1. Treat the diagram as navigation evidence, not proof completion. Before
   saying a block is proved, cite the checker/analyzer artifact named by
   `$formal-proof-workflow`.
