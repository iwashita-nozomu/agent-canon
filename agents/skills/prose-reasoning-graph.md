# prose-reasoning-graph
<!--
@dependency-start
responsibility Documents prose-reasoning-graph analysis and skill handoff workflow.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py builds SQLite-backed graph projections
downstream implementation ../../.agents/skills/prose-reasoning-graph/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../.claude/skills/prose-reasoning-graph/SKILL.md mirrors this workflow for Claude-compatible runtimes
downstream design ../../documents/tools/prose_reasoning_graph.md documents CLI usage
@dependency-end
-->

## Purpose

`prose-reasoning-graph` is the overlay skill for analyzing prose as a typed
graph before asking an LLM or writing skill to rewrite it. It converts existing
Markdown/plain text into a SQLite-backed intermediate graph, runs layer
diagnostics, explains graph findings in natural language, and emits handoff
packets for existing writing, research, review, experiment, and artifact skills.

It does not replace `$long-form-writing`, `$report-writing`,
`$academic-writing`, `$paper-writing`, `$literature-survey`,
`$structure-planning`, `logic-gap-review`, `citation-evidence-review`,
`$experiment-lifecycle`, or `$result-artifact-writeout`. It reduces their
context burden by giving them structured evidence, edit operations, and rewrite
packets.

## Use When

- Existing prose should be converted into a graph/DSL-like intermediate form.
- Paragraph order, paragraph-to-paragraph connection, or paragraph-internal
  naturalness needs evidence before rewrite.
- A draft needs split, merge, bridge, or reorder operations.
- A paper, scholarly note, report, or experiment plan needs logic-hole,
  citation/evidence, or experiment-design triage before drafting.
- An LLM should receive a compact rewrite packet rather than re-inferring the
  whole document structure from raw prose.

## Standard Sequence

1. Store graph DB and generated outputs under the active run bundle, report, or
   other task-local artifact directory.
1. Run `ingest` on the source Markdown/plain text with `--stats-out`.
1. Run `analyze --profile <writing|logic|experiment|report|academic|paper|all>`
   with `--stats-out`.
1. Export `project`, `lint`, `explain`, and `integrate` outputs with
   `--stats-out`; read the stats JSON before opening larger artifacts.
1. For each proposed operation that should be rewritten, export
   `rewrite-packet --op <operation-id>`.
1. Export `skill-handoff` and pass it to the receiving skill or reviewer.
1. Treat graph diagnostics as advisory evidence. Final prose, review, and
   publication authority stays with the receiving skill.

## Required Outputs

```text
prose_graph_db=<path>
prose_graph_projection=<path>
prose_graph_diagnostics=<path>
prose_graph_explanation=<path>
prose_graph_integration_plan=<path>
prose_graph_handoff=<path>
prose_graph_rewrite_packet=<path|not_required>
prose_graph_stats=<path>
```

## Literature Boundary

The graph layers are intentionally plural. RST motivates rhetorical relations
and nucleus/satellite-style organization, PDTB motivates local discourse
relations, eRST motivates graph-shaped discourse overlays, Toulmin/AIF motivates
claim/evidence reasoning, argumentative zoning motivates scholarly move labels,
and reproducible experiment literature motivates hypothesis/metric/baseline
planning. Do not collapse these layers into one total order until a projection
or receiving skill asks for reader order.
