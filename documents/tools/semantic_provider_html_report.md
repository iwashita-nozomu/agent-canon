# semantic_provider_html_report.py
<!--
@dependency-start
contract reference
responsibility Documents the Quarto-backed semantic provider HTML report route.
upstream design ./semantic_index.md defines semantic provider comparison and candidate authority boundaries
upstream design ../../agents/skills/html-output.md owns HTML artifact generation and validation
upstream environment ../../bootstrap/container/image/dependencies.toml supplies Quarto, embedded Pandoc, and the offline link checker
upstream design ../prose-reasoning-graph/dsl-spec.md defines shared graph visualization projection and adapter contract
upstream implementation ../../tools/analysis/search/reporting/semantic_provider_html_report.py renders provider comparison HTML
downstream implementation ../../tests/agent_tools/test_semantic_provider_html_report.py tests renderer behavior
@dependency-end
-->

`tools/analysis/search/reporting/semantic_provider_html_report.py` renders
`agent-canon semantic-index compare-providers` JSON as a static HTML report
through the installed Quarto CLI and its embedded Pandoc. Quarto owns general
document layout, HTML serialization, and local-resource handling; the report
tool supplies comparison facts and its domain-specific SVG figure.

This report is the semantic-provider comparison adapter for the shared graph
visualization contract. `agent-canon semantic-index compare-providers` owns
provider comparison data and candidate authority boundaries. The HTML report is
a projection artifact over provider nodes, candidate-delta edges, overlap
metrics, and source locators that can be mapped into the DSL object model in
[documents/prose-reasoning-graph/dsl-spec.md](../prose-reasoning-graph/dsl-spec.md).

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
python3 tools/analysis/search/reporting/semantic_provider_html_report.py \
  --compare-json reports/agents/<run-id>/semantic_provider_compare.json \
  --output reports/agents/<run-id>/semantic_provider_compare.html
```

The default output is static and does not execute code or start a server. Quarto
is invoked with `--no-execute`; local assets remain beside the HTML so the report
works without a network connection. The generated `.qmd` is rendered in an
owned minimal Quarto project with no pre-render or post-render scripts, so a
caller project's hooks are not inherited even when `TMPDIR` is nested there. Pass
`--embed-resources` only when a single HTML file is needed. The command inspects the generated Quarto source, renders
HTML, and checks local links with the repository's offline Lychee configuration.
It prints a JSON readback with source/config/asset hashes, Quarto and embedded
Pandoc versions, exact renderer argv, the output hash, and the validation result.

Quarto/Pandoc diagnostics and failure status are preserved. The report command
distinguishes missing input assets, invalid JSON/Quarto source, unavailable
Quarto, rendering failure, and output validation failure.

The first figure is `Provider Delta To Shared Candidate Logic`. It shows that
left and right embedding providers can produce different search or merge
candidate deltas while the authority remains the existing
responsibility-scoped candidate logic.

The report is review evidence. Indexing, document classification, ownership
labels, and merge/delete decisions stay with the semantic-index workflow and
its reviewers. The SVG remains a local report asset and does not introduce a
second general-purpose HTML renderer.
