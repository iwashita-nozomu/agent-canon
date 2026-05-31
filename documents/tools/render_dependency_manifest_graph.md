<!--
@dependency-start
responsibility Documents dependency manifest graph report rendering.
upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT graph reports.
upstream implementation ../../tools/agent_tools/check_dependency_graph.sh writes dependency graph TSV artifacts.
upstream design ../dependency-manifest-design.md defines dependency manifest semantics.
downstream implementation ../../tests/agent_tools/test_render_dependency_manifest_graph.py tests renderer behavior.
@dependency-end
-->

# render_dependency_manifest_graph.py

Use this read-only tool when a review needs a compact dependency-manifest graph
instead of raw edge output.

```bash
bash tools/agent_tools/check_dependency_graph.sh --graph-tsv reports/dependency_graph.tsv
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --graph-tsv reports/dependency_graph.tsv \
  --markdown-out reports/dependency_graph.md \
  --dot-out reports/dependency_graph.dot
```

The Markdown report summarizes node count, edge count, cycles, broken targets,
and high-degree nodes. The DOT output is suitable for Graphviz or CI artifacts.
The report is review evidence; it does not replace the dependency header
checker.

For PR gates with known graph-cycle debt, use the graph report together with:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh \
  --fail-missing \
  --cycle-report-only \
  --report-dir reports/dependency-review/agent-canon-pr
```

The wrapper still blocks missing or malformed manifests, but cycles remain a
reported review artifact instead of hidden terminal output.
