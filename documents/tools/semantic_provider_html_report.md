# semantic_provider_html_report.py
<!--
@dependency-start
responsibility Documents the semantic provider HTML report renderer.
upstream design ../semantic_index.md defines semantic provider comparison and candidate authority boundaries
upstream design ../../agents/skills/html-experiment-report.md defines HTML experiment report workflow
upstream implementation ../../tools/agent_tools/semantic_provider_html_report.py renders provider comparison HTML
downstream implementation ../../tests/agent_tools/test_semantic_provider_html_report.py tests renderer behavior
@dependency-end
-->

`tools/agent_tools/semantic_provider_html_report.py` renders
`agent-canon semantic-index compare-providers` JSON as a self-contained HTML
report.

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

The report is review evidence only. It does not rerun indexing, classify
documents, label ownership, or authorize merge/delete decisions.
