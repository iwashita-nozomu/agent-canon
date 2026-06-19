# semantic_provider_html_report.py
<!--
@dependency-start
contract reference
responsibility Documents the semantic provider HTML report renderer.
upstream design ../semantic_index.md defines semantic provider comparison and candidate authority boundaries
upstream design ../../agents/skills/html-experiment-report.md defines HTML experiment report workflow
upstream design ../prose-reasoning-graph/dsl-spec.md defines shared graph visualization projection and adapter contract
upstream implementation ../../tools/agent_tools/semantic_provider_html_report.py renders provider comparison HTML
downstream implementation ../../tests/agent_tools/test_semantic_provider_html_report.py tests renderer behavior
@dependency-end
-->

`tools/agent_tools/semantic_provider_html_report.py` renders
`agent-canon semantic-index compare-providers` JSON as a self-contained HTML
report.

This report is the semantic-provider comparison adapter for the shared graph
visualization contract. `agent-canon semantic-index compare-providers` owns
provider comparison data and candidate authority boundaries. The HTML report is
a projection artifact over provider nodes, candidate-delta edges, overlap
metrics, and source locators that can be mapped into the DSL object model in
`documents/prose-reasoning-graph/dsl-spec.md`.

Adapter mapping uses each provider result, candidate document, and shared or
divergent match as a source-truth anchor with source span metadata where the
semantic-index output includes one. Providers, candidate artifacts, ranked
cells, and comparison groups become node record entries; overlap, divergence,
ranking, and responsibility relations become typed relation edge record
entries. `payload_json` carries provider name, score, rank, path, document id,
responsibility bucket, and comparison metadata. The HTML report is a projection
view product over this lower graph, with reader-state and macro-claim context
provided by the provider comparison review packet.

Use it after a provider comparison artifact already exists:

```bash
python3 tools/agent_tools/semantic_provider_html_report.py \
  --compare-json reports/agents/<run-id>/semantic_provider_compare.json \
  --output reports/agents/<run-id>/semantic_provider_compare.html
```

The first figure is `Provider Delta To Shared Candidate Logic`. It shows that
left and right embedding providers can produce different search or merge
candidate deltas while the authority remains the existing
responsibility-scoped candidate logic.

The report is review evidence. Indexing, document classification, ownership
labels, and merge/delete decisions stay with the semantic-index workflow and
its reviewers.
