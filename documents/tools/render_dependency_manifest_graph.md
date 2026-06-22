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

Use this read-only tool when a review needs a compact dependency-manifest graph
instead of raw edge output. The tool can render Markdown, Graphviz DOT, and a
self-contained HTML code-space viewer from the same graph TSV artifact.

This tool is the dependency-manifest graph adapter for the shared Graph DSL Core
projection contract. `check_dependency_graph.sh` keeps dependency validation
authority. This renderer maps TSV source/target edges into inspectable
projection artifacts: Markdown summary, DOT, and HTML viewer. Future reusable
graph UI work should flow through the projection payload described in
`documents/structured-analysis/graph-dsl.md`; this tool keeps the
domain-specific TSV extraction and compatibility route.

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

Adapter mapping uses each dependency manifest entry as the source record or
native locator and records the manifest source span when available. Repository
files, logical artifacts, or checker findings become node records; dependency,
upstream, downstream, and coverage relations become typed relation entries as
layer-qualified edge record rows under `deps`. `payload_json` carries native
locators such as path, line, dependency kind, checker id, and graph TSV row.
The exported Markdown, DOT, and
HTML views are projection products over this lower graph of dependency facts,
with reader-state and macro-claim context supplied by the surrounding review
packet.

```bash
bash tools/agent_tools/check_dependency_graph.sh --graph-tsv reports/dependency_graph.tsv
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --graph-tsv reports/dependency_graph.tsv \
  --markdown-out reports/dependency_graph.md \
  --dot-out reports/dependency_graph.dot \
  --html-out reports/dependency_graph.html
```

The Markdown report summarizes node count, edge count, cycles, broken targets,
and high-degree nodes. The DOT output is suitable for Graphviz or CI artifacts.
The HTML output is a browser-readable graph UI with search, direction/kind
filters, focus-depth navigation, SVG graph rendering, and a node inspector.
The viewer keeps the complete graph payload in the artifact but bounds the
initial DOM/SVG render to high-degree nodes when a filtered view is too large;
search or focus filters should be used for local inspection of large graphs.
Zoom changes resize the existing SVG instead of rebuilding the graph.
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
