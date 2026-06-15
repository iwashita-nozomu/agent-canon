<!--
@dependency-start
responsibility Documents algorithm_flowchart.py operator usage.
upstream implementation ../../tools/agent_tools/algorithm_flowchart.py renders Mermaid diagrams.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds Algorithm Expansion IR.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py builds Lemma Dependency Graphs.
upstream implementation ../../tools/agent_tools/proof_path_analyzer.py checks proof-status overlays.
upstream implementation ../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections from IR facts.
upstream design ../../agents/skills/algorithm-flowchart.md defines the skill workflow.
upstream design ../prose-reasoning-graph/dsl-spec.md defines shared graph visualization projection and adapter contract.
upstream design kkt_equation_section.md documents KKT equation prose generation from Algorithm IR facts.
downstream implementation ../../tests/agent_tools/test_algorithm_flowchart.py tests CLI behavior.
@dependency-end
-->

# algorithm_flowchart.py

`algorithm_flowchart.py` renders Algorithm Expansion IR as a Mermaid block
chart. When supplied, LemmaGraph JSON and `proof_status.json` are overlaid so
the diagram shows which implementation blocks are verified, open, external
assumptions, operational assumptions, or terminal negative results.

The tool does not prove mathematics. It is a navigation view over artifacts
produced by `algorithm_expansion_ir.py`, `algorithm_lemma_graph.py`, and
`proof_path_analyzer.py`.

Within AgentCanon's shared graph visualization model, this tool is the
Algorithm Expansion IR / LemmaGraph adapter. Algorithm extraction, lemma-graph
construction, and proof-status checks keep domain authority. The Mermaid,
Markdown, and JSON outputs are DSL-style projection artifacts over source
locators, IR node ids, lemma graph ids, proof-status payloads, and projection
edges. Future shared visual UI behavior should be implemented through the graph
projection contract in `documents/prose-reasoning-graph/dsl-spec.md`, while
this tool keeps the algorithm/proof adapter responsibilities.

Adapter mapping uses each Algorithm Expansion IR block, lemma node, and
proof-status entry as a source-truth anchor with source span metadata when the
producer provides it. Blocks, lemmas, proof obligations, and status overlays
become node record entries; control-flow, lemma-dependency, proof-support, and
status-overlay links become typed relation edge record entries. `payload_json`
carries native ids, path or symbol locators, proof status, theorem names, and
checker provenance. Mermaid, Markdown, and JSON outputs are projection view
products over this lower graph, with reader-state and macro-claim context
provided by the proof or algorithm review packet.

## Typical Use

```bash
python3 tools/agent_tools/algorithm_expansion_ir.py \
  --python-symbol python/jax_util/optimizers/pdipm.py::_solve \
  --target-theorem "PDIPM local convergence" \
  --format json \
  --out lean/pdipm_convergence/pdipm_solve_ir.json

python3 tools/agent_tools/algorithm_lemma_graph.py \
  --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
  --target-profile local_convergence \
  --target-profile solver_chain \
  --format json \
  --out lean/pdipm_convergence/pdipm_solver_chain_lemma_graph.json

python3 tools/agent_tools/algorithm_flowchart.py \
  --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
  --lemma-graph lean/pdipm_convergence/pdipm_solver_chain_lemma_graph.json \
  --proof-status lean/pdipm_convergence/proof_status.json \
  --include-code-facts \
  --format markdown \
  --out lean/pdipm_convergence/pdipm_recursive_minimal_flowchart.md
```

For a one-shot AST route, pass `--python-symbol` directly:

```bash
python3 tools/agent_tools/algorithm_flowchart.py \
  --python-symbol python/jax_util/optimizers/pdipm.py::_solve \
  --target-theorem "PDIPM local convergence" \
  --format markdown
```

## Inputs

- `--ir-json`: Algorithm Expansion IR JSON. Use this when the proof topic
  already materialized IR under `lean/<theme>/`.
- `--python-symbol`: AST-only direct route in `path.py::qualname` format.
  This builds IR in memory before rendering.
- `--lemma-graph`: optional, repeatable LemmaGraph JSON files. These provide
  graph-derived proof statuses and source-node / code-fact ownership.
- `--proof-status`: optional proof overlay. `code_derived_facts[].source_id`
  values that point to lemma nodes or IR facts are used to color the affected
  blocks.
- `--include-code-facts`: render assignment/default/return facts as subordinate
  blocks. Use this when the important recurrence, stopping, or residual
  equation is a code fact rather than a function-level IR node.
- `--view`: selects the projection.
  - `proof`: overlays LemmaGraph and `proof_status.json` and includes proof
    status labels.
  - `runtime`: omits proof-status labels and proof-only edges. By default it
    also drops theorem-slice-excluded bookkeeping nodes; use
    `--include-bookkeeping` for a full implementation expansion.
  - `core`: omits proof-status labels and keeps mathematical state-transition,
    solver, certificate, diagnostic, and tagged equation-fact blocks.
- `--include-bookkeeping`: keeps theorem-slice-excluded bookkeeping nodes in
  `runtime` / `core` views.

## Output

Formats:

- `markdown`: a report with status counts, fenced Mermaid, and block table.
- `mermaid`: only the Mermaid flowchart source.
- `json`: machine-readable nodes, edges, counts, and Mermaid source.

Color classes:

- `verified`: checker-backed fragment or verified overlay.
- `assumption`: mathematical assumption node.
- `external_assumption`: backend or external source boundary.
- `operational_assumption`: implemented trace premise.
- `open`: open witness, blocker, or `unverified_with_next_witness`.
- `unprovable_under_assumptions` / `refuted`: terminal negative result.
- `unverified`: no proof overlay has been attached yet.

## Limits

The chart is a visualization layer over `proof_path_analyzer.py`,
Algorithm Expansion IR, LemmaGraph, and `proof_status.json`. Regenerate the
chart after changing implementation code or any upstream graph artifact.

The `--view runtime` and `--view core` inputs above are the implementation-only
diagram routes. Keep proof-boundary material in the `proof` view and proof
artifacts, and use `kkt_equation_section.py` for KKT equation prose backed by IR
code facts.
