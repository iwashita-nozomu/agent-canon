<!--
@dependency-start
contract reference
responsibility Documents dependency manifest graph report rendering.
upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT graph reports.
upstream implementation ../../tools/agent_tools/check_dependency_graph.sh writes dependency graph TSV artifacts.
upstream design ../dependency-manifest-design.md defines dependency manifest semantics.
upstream design ../structured-analysis/graph-dsl.md defines shared graph storage and projection contract.
upstream design ../prose-reasoning-graph/dsl-spec.md defines prose graph adapter vocabulary when dependency graph views are embedded in prose workflows.
downstream implementation ../../tests/agent_tools/test_render_dependency_manifest_graph.py tests renderer behavior.
@dependency-end
-->

# render_dependency_manifest_graph.py

Use this read-only tool when a review needs a repo-local dependency-manifest
graph representation instead of raw edge output. The tool can render a
versioned Graph IR JSON, Markdown, Graphviz DOT, and a self-contained HTML
graph workbench from the same graph TSV artifact.

This tool is the dependency-manifest graph adapter for the shared Graph DSL Core
projection contract. `check_dependency_graph.sh` keeps dependency validation
authority. This renderer maps TSV source/target edges into a repo-local lower
graph and inspectable projection artifacts. The Graph IR is the durable
intermediate representation for local graph tooling; Markdown, DOT, and HTML
are projection views over it. Future reusable graph UI work should flow through
the projection payload described in
`documents/structured-analysis/graph-dsl.md`; this tool keeps the
domain-specific TSV extraction and compatibility route. When dependency graph
views are embedded in prose workflows, prose-specific vocabulary remains owned
by `documents/prose-reasoning-graph/dsl-spec.md`.

## Reader Map

- Owns the usage contract for rendering dependency manifests into Mermaid,
  Graphviz, HTML, and summary artifacts.
- Main path: the opening description explains the render target, and Evidence
  And Assumption Ledger records sources, assumptions, and validation.
- Read this when producing visual dependency-manifest projections from an
  existing graph artifact.
- Boundary: this tool renders validated dependency data; schema and dependency
  semantics remain with the manifest and validation docs.

## Evidence And Assumption Ledger

- Evidence sources:
  `../structured-analysis/graph-dsl.md`,
  `../prose-reasoning-graph/dsl-spec.md`,
  `../../tools/agent_tools/render_dependency_manifest_graph.py`, and
  `../../tools/agent_tools/check_dependency_graph.sh`.
- Assumption:
  DSL vocabulary in this document names Graph DSL Core projection terms.
  Dependency validation remains with `check_dependency_graph.sh`.
- Parent-doc alignment:
  `../structured-analysis/graph-dsl.md` owns storage vocabulary. The prose graph
  DSL owns prose-specific projection vocabulary used when dependency graph views
  appear inside prose workflows.

Adapter mapping uses each dependency manifest entry as the source-truth anchor
and records the manifest source span when available. Repository files,
logical artifacts, or checker findings become `repo_path` node record entries;
dependency, upstream, downstream, and coverage relations become typed relation
edge record entries. The IR also infers `directory` nodes and `contains` edges
from repository path prefixes so local graph tools can recover directory
containment without reparsing display labels. `payload_json` carries native
locators such as path, line, dependency kind, checker id, graph TSV row, and
containment parent/child paths. The exported Markdown, DOT, and HTML views are
projection view products over this lower graph of dependency facts, with
reader-state and macro-claim context supplied by the surrounding review packet.

```bash
bash tools/agent_tools/check_dependency_graph.sh --graph-tsv reports/dependency_graph.tsv
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --graph-tsv reports/dependency_graph.tsv \
  --ir-out reports/dependency_graph.ir.json \
  --markdown-out reports/dependency_graph.md \
  --dot-out reports/dependency_graph.dot \
  --html-out reports/dependency_graph.html
```

The IR output uses schema `agent_canon.graph_ir.v1`. It keeps source-truth
locators, graph-local node and edge records, dependency relation metadata,
metrics, display labels, and projection hints such as `code_territory_map` and
`dense_group_static_graph`. Full paths remain in `text`, `source_locator`, and
`payload_json`; shortened labels live only in `display` fields for visualization.
For compatibility, `summary.nodes` and `summary.edges` remain the dependency
projection counts. Directory containment is reported separately through
`summary.directoryNodes`, `summary.containmentEdges`, `summary.totalNodes`, and
`summary.totalEdges`.

The Markdown report summarizes node count, edge count, cycles, broken targets,
and high-degree nodes. The DOT output is suitable for Graphviz or CI artifacts.
The HTML output is a single-file browser-readable graph workbench. Its primary
view is a complete static graph surface: header metrics, Voronoi-style code
territory map, dense path-level SVG map using shortened node labels,
fixed-viewport `viewBox` zoom/pan controls, complete dependency node table,
complete dependency edge table, and a directory-containment table. DOT and the
interactive dependency graph remain dependency-projection views; containment
stays in the IR and dedicated HTML table. A secondary filtered explorer keeps
search, direction/kind filters, focus-depth navigation, SVG graph rendering,
and a node inspector for local inspection.

The HTML graph workbench targets ordinary browser execution, including the VS
Code Integrated Browser and Microsoft Live Preview local-server path. JavaScript
is part of the canonical interaction contract: zoom buttons, range input, wheel
zoom, drag-pan, and filtered explorer behavior all run in the same HTML file.
The static SVG and tables remain present in the markup before JavaScript runs,
but no companion `*_zoom_*.html` files are generated. Generic Webview-style
previews that disable scripts can display the complete static graph and tables,
but they are not the canonical zoom backend for this tool.

These reports are review evidence. The dependency header checker remains the
source for dependency pass/fail decisions, and generated HTML is a reproducible
projection artifact.

For PR gates with known graph-cycle debt, use the graph report together with:

```bash
PR_CHECK_TMP="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-pr-check.XXXXXX")"
trap 'rm -rf "${PR_CHECK_TMP}"' EXIT
bash tools/agent_tools/run_repo_dependency_review.sh \
  --fail-missing \
  --cycle-report-only \
  --report-dir "${PR_CHECK_TMP}/dependency-review/agent-canon-pr"
```

The wrapper still blocks missing or malformed manifests, but cycles remain a
reported review artifact instead of hidden terminal output. PR gates keep this
artifact under the temp directory and run `generated_artifact_guard.py` before
closeout so regenerated reports do not remain in `reports/`.
