---
name: algorithm-flowchart
description: Use when rendering Python AST-derived Algorithm Expansion IR, LemmaGraph, and proof_status overlays into Mermaid block charts that show the implemented iterative algorithm and proof state.
---

<!--
@dependency-start
responsibility Exposes AST/IR-derived algorithm Mermaid flowcharts to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/algorithm-flowchart.md canonical skill document
upstream design ../../../agents/skills/algorithm-proof-exploration.md algorithm IR and lemma graph workflow.
upstream design ../../../agents/skills/formal-proof-workflow.md proof status workflow.
upstream implementation ../../../tools/agent_tools/algorithm_flowchart.py renders Mermaid diagrams.
upstream implementation ../../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections from IR facts.
@dependency-end
-->

# Algorithm Flowchart

1. Read `agents/skills/algorithm-flowchart.md`.
1. Use this with `$algorithm-proof-exploration` or `$formal-proof-workflow`
   when the task asks what iterative algorithm is implemented, where solver
   chain blocks are, or which blocks are verified/open/external.
1. Generate or reuse Algorithm Expansion IR first. Prefer:
   `python3 tools/agent_tools/algorithm_expansion_ir.py --python-symbol <path.py::qualname> --target-theorem "<theorem>" --format json --out <ir.json>`.
1. Generate or reuse one or more LemmaGraph files when proof-state coloring is
   needed:
   `python3 tools/agent_tools/algorithm_lemma_graph.py --ir-json <ir.json> --target-profile <profile> --format json --out <graph.json>`.
1. Render the chart mechanically:
   `python3 tools/agent_tools/algorithm_flowchart.py --ir-json <ir.json> --lemma-graph <graph.json> --proof-status <proof_status.json> --include-code-facts --format markdown --out <flowchart.md>`.
   Use `--view runtime` for implementation-only flow and
   `--view core --include-code-facts` for the proof-relevant mathematical /
   solver core without proof-only labels or branches.
1. Do not hand-draw or manually maintain diagrams for implementation-derived
   algorithms. If code or proof overlays change, regenerate IR, graph, proof
   analyzer output, and flowchart in that order.
1. Do not hand-write KKT solver-chain equation prose when it can be generated
   from IR. Use `python3 tools/agent_tools/kkt_equation_section.py` with the
   current PDIPM/KKT/MINRES IR files.
1. Treat the diagram as navigation evidence, not proof completion. Before
   saying a block is proved, cite the checker/analyzer artifact named by
   `$formal-proof-workflow`.
