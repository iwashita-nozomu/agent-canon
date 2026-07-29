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
upstream design ../../../agents/skills/code-visualization.md sole public visualization owner and typed projection contract.
upstream implementation ../../../tools/agent_tools/visualization_contract.py owns ToolCall, identity, manifest, readback, and coverage serialization.
downstream implementation ../../../tests/tools/test_fix_mermaid.py checks syntax-only Mermaid formatting.
@dependency-end
-->

# Algorithm Flowchart

## Visualization Adapter Boundary

Build a complete `VisualizationSourceUniverse` containing every selected
JIT/HLO operation and edge, branch, phase, backend/dtype field, proof/evidence
item, source locator, helper, and timing item, then hand it to
`$code-visualization`. Serialize the canonical coverage-owner ToolCall first and
the algorithm adapter ToolCall second. Use `serialize_projection_identity` for
every locator and `serialize_projection_coverage_manifest` for the marker; call
no private owner helper. This skill owns source facts and exactly one Mermaid
rendering only, with no table fallback. Run
`tools/bin/agent-canon docs format <artifact.md>`, then
`readback_projection` and `validate_projection_coverage(..., readback=...)`.
Only that typed result is final; Rust owns syntax only. `--include-code-facts`
is reversible view-only state and cannot change the artifact or universe.

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-flowchart --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
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
