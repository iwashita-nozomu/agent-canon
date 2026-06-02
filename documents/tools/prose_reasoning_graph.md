<!--
@dependency-start
responsibility Documents prose_reasoning_graph.py usage and contract.
upstream design ../prose-reasoning-graph/dsl-spec.md normative graph and DSL contract
upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py builds SQLite-backed prose reasoning graphs
upstream design ../../agents/workflows/workflow-references.md discourse, argument, and writing prior art
upstream design ../../agents/skills/prose-reasoning-graph.md prose graph skill contract
downstream implementation ../../tests/agent_tools/test_prose_reasoning_graph.py validates CLI behavior
@dependency-end
-->

# prose_reasoning_graph.py

`prose_reasoning_graph.py` turns Markdown or plain text into a temporary
SQLite-backed prose reasoning graph. The database is an intermediate analysis
artifact, not a durable source of truth. Use the exported projection,
diagnostics, explanation, and rewrite packets as evidence for writing skills,
reviewers, and LLM rewrite passes.

The durable graph/DSL contract lives in
[Prose Reasoning Graph DSL Specification](../prose-reasoning-graph/dsl-spec.md).
This tool document explains command usage and operator flow; it must not become
a second copy of the DSL vocabulary.

The graph has explicit layers for source spans, form, concepts, genre moves,
discourse relations, argument claims, evidence, experiment planning,
presentation order, diagnostics, edit operations, natural-language explanation,
and projection metadata. The canonical prose source is one text-anchored
semantic graph: sentence or EDU anchors and typed relations carry the
source-truth, while macro-claims, subtopics, and reader-state transitions are
derived projection views over the same graph. Section and paragraph nodes remain
source form containers in the current MVP. This follows the design choice from
Annotation Graphs, RST, PDTB, RST dependency views, eRST, Toulmin/AIF,
argumentative zoning, and reproducible experiment-planning literature: prose
structure is easier to inspect as a typed graph with overlays than as a single
tree or a sequential label pipeline.

Projection views may recommend a reader-facing format such as prose,
bulleted list, ordered list, table, figure, or equation. The recommendation is
advisory evidence for a rewrite or renderer: the canonical graph still owns the
source anchors and typed relations, while the presentation format says how that
subgraph may be easier to read.

`ingest` also accepts `--prompt` and `--prompt-file` for corpus/domain
inference. The exported projection includes `corpus_hints`, ranked from user
prompt and source-text keywords. Treat these hints as a default corpus profile
for retrieval, examples, and evaluation norms; they are not citations or proof.

## Command Flow

```bash
python3 tools/agent_tools/prose_reasoning_graph.py ingest notes/draft.md --db reports/agents/<run-id>/prose.sqlite --prompt-file reports/agents/<run-id>/user_request_contract.md --stats-out reports/agents/<run-id>/prose_ingest.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py analyze --db reports/agents/<run-id>/prose.sqlite --profile all --stats-out reports/agents/<run-id>/prose_analyze.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py project --db reports/agents/<run-id>/prose.sqlite --profile all --out reports/agents/<run-id>/prose_projection.yaml --stats-out reports/agents/<run-id>/prose_project.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py lint --db reports/agents/<run-id>/prose.sqlite --profile all --out reports/agents/<run-id>/prose_diagnostics.md --stats-out reports/agents/<run-id>/prose_lint.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py explain --db reports/agents/<run-id>/prose.sqlite --profile all --out reports/agents/<run-id>/prose_explanation.md --stats-out reports/agents/<run-id>/prose_explain.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py integrate --db reports/agents/<run-id>/prose.sqlite --profile all --out reports/agents/<run-id>/prose_integration.md --stats-out reports/agents/<run-id>/prose_integrate.stats.json
python3 tools/agent_tools/prose_reasoning_graph.py skill-handoff --db reports/agents/<run-id>/prose.sqlite --profile all --out reports/agents/<run-id>/prose_handoff.md --stats-out reports/agents/<run-id>/prose_handoff.stats.json
```

Use `rewrite-packet --op <operation-id>` after `integrate` when a specific
split, merge, bridge, or reorder operation should be handed to an LLM.
Use `--stats-out` by default in agent workflows so stdout stays bounded to the
pass marker and stats path; read the JSON stats artifact before opening larger
projection, diagnostics, explanation, or handoff files.

## Profiles

- `writing`: long-form section and paragraph flow.
- `logic`: claim support, bridge, and logic-gap triage.
- `experiment`: hypothesis, metric, baseline, expected result, and report
  readiness.
- `report`: evidence traceability and reader-facing report structure.
- `academic`: notation/logic/citation-aware scholarly prose.
- `paper`: paper section contract and citation-evidence review.
- `all`: all handoffs and all graph layers.

## Skill Handoff

The `skill-handoff` command emits explicit entries for `$long-form-writing`,
`$report-writing`, `$academic-writing`, `$paper-writing`, `$literature-survey`,
`$structure-planning`, `logic-gap-review`, `citation-evidence-review`,
`$experiment-lifecycle`, and `$result-artifact-writeout`. The handoff gives
each receiving skill the DB path plus commands for projection, diagnostics,
natural-language explanation, and rewrite planning.

The receiving skill remains authoritative for its own review gate. A graph
diagnostic can say a claim is unsupported or a transition is weak; it cannot
approve a paper, settle a citation, merge a PR, or change repository policy.
