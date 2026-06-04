<!--
@dependency-start
responsibility Defines document canon and duplicate-document analysis for structured analysis.
upstream design README.md structured analysis package index
upstream design database-design.md defines document-canon DB layer placement
upstream design ../rust-agent-tool-migration.md Rust tool migration policy
upstream design ../../agents/skills/document-canon-cleanup.md document cleanup workflow
upstream implementation ../../rust/agent-canon/src/structured_analysis.rs Rust structured-analysis CLI
downstream implementation ../../tools/agent_tools/noncanonical_document_inventory.py forwards legacy calls to the Rust CLI
@dependency-end
-->

# Document Canon Analysis Adapter

この文書は、文書の正本候補、runtime mirror、generated report、closed issue record、
stale name、duplicate heading を structured analysis に取り込む adapter contract を定義する。

## Rust CLI

正実装は Rust CLI である。

```bash
agent-canon structured-analysis document-inventory \
  --root . \
  --json-out "$GRAPH_HOME/document_inventory.json" \
  --markdown-out "$GRAPH_HOME/exports/document_inventory.md"

agent-canon structured-analysis import-document-inventory \
  --db "$GRAPH_HOME/prose_graph.sqlite" \
  --json "$GRAPH_HOME/document_inventory.json"
```

Python の `tools/agent_tools/noncanonical_document_inventory.py` は caller warning
付きの legacy migration shim である。新しい workflow / hook /
structured-analysis integration は Rust CLI を参照する。shim の警告が出た場合は、
呼び出し元を Rust CLI へ移行してから元 task へ戻る。

## Finding Kinds

| Kind | Meaning | Structured severity |
| --- | --- | --- |
| `generated_report` | `reports/...` が source policy と混同される可能性。 | `info` |
| `closed_issue_record` | closed issue record が active scope と混同される可能性。 | `info` |
| `missing_dependency_manifest` | source doc に dependency manifest がない。 | `blocker` |
| `stale_name_candidate` | path name が old / copy / duplicate / legacy / snapshot / stale を示す。 | `warn` |
| `duplicate_heading_candidate` | active document が同じ H1 title を共有する。 | `warn` |

## DB Mapping

| Inventory field | DB target |
| --- | --- |
| `documents[]` | `nodes.layer = document-canon`, `kind = document_record` |
| `findings[]` | `nodes.layer = document-canon`, `kind = finding` |
| finding target path | `edges.layer = document-canon`, `kind = targets_document` |
| finding canonical path | `edges.layer = document-canon`, `kind = references_canonical` |
| finding severity/rule/message | `diagnostics.layer = document-canon` |
| inventory summary | `metadata.key = document_canon_inventory` |

Document canon findings are structural cleanup evidence. They do not prove prose
quality, citation validity, code behavior, or merge readiness.

## Use With Prose Graph

Document canon evidence joins the prose graph at report claim and source-packet
selection time.

```text
report claim
  -> source document path
  -> document-canon document_record
  -> duplicate / mirror / stale / missing-header finding
  -> cleanup action or explicit accepted exception
```

This lets a report explain when a source is canonical, duplicated, generated,
or only historical before a writing skill relies on it.
