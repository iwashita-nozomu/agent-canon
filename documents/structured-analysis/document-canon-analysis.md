<!--
@dependency-start
contract reference
responsibility Defines document canon and duplicate-document analysis for structured analysis.
upstream design README.md structured analysis package index
upstream design database-design.md defines document-canon DB layer placement
upstream design ../rust-agent-tool-migration.md Rust tool migration policy
upstream design ../../agents/skills/document-canon-cleanup.md document cleanup workflow
upstream implementation ../../rust/agent-canon/src/structured_analysis.rs Rust structured-analysis CLI
@dependency-end
-->

# Document Canon Analysis Adapter

この文書は、文書の正本候補、runtime mirror、generated report、closed issue history、
stale name、duplicate heading を structured analysis に取り込む adapter contract を定義する。

## Reader Map

- Owns document-canon and duplicate-document analysis as a structured-analysis
  adapter.
- Main path: Evidence And Assumption Ledger, Rust CLI, Finding Kinds,
  Historical Records, DB Mapping, and Query Surface.
- Read this before importing document inventory or canon-cleanup findings into
  the structured-analysis DB.
- Boundary: this adapter classifies document records and findings; cleanup
  decisions still follow the document-canon workflow.

## Evidence And Assumption Ledger

- Evidence sources:
  `database-design.md`, `README.md`, and
  `../../rust/agent-canon/src/structured_analysis.rs`.
- Assumptions:
  Document canon inventory JSON uses the implemented keys `documents`,
  `findings`, and `historical_records`; graph storage uses the implemented
  `document-canon` layer, node kinds `document_record`, `finding`,
  `historical_record`, edge kinds `targets_document` and
  `references_canonical`, and metadata key `document_canon_inventory`.
- Parent-doc alignment:
  `database-design.md` owns the shared table contract. This adapter owns the
  document-inventory classification and import mapping.

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

Old Python document-inventory entrypoints are retired. New workflow, hook, and
structured-analysis integration references the Rust CLI directly.

## Finding Kinds

| Kind | Meaning | Structured severity |
| --- | --- | --- |
| `generated_report` | `reports/...` が source policy と混同される可能性。 | `info` |
| `missing_dependency_manifest` | source doc に dependency manifest がない。 | `blocker` |
| `stale_name_candidate` | path name が old / copy / duplicate / legacy / snapshot / stale を示す。 | `warn` |
| `duplicate_heading_candidate` | active document が同じ H1 title を共有する。 | `warn` |

## Historical Records

| Kind | Meaning | Structured severity |
| --- | --- | --- |
| `closed_issue_record` | `issues/closed/...` の履歴 record。active cleanup scope ではなく、同名の新 scope は `issues/open/...` に作る。 | diagnostic なし |
| `stale_name_candidate` on `issues/closed/...` | closed issue filename に legacy / old などの語が含まれる履歴 record。closed issue の immutable history として扱う。 | diagnostic なし |

## DB Mapping

| Inventory field | DB target |
| --- | --- |
| `documents` | table `nodes`; layer `document-canon`; kind `document_record` |
| `findings` | table `nodes`; layer `document-canon`; kind `finding` |
| `historical_records` | table `nodes`; layer `document-canon`; kind `historical_record` |
| finding target path | table `edges`; layer `document-canon`; kind `targets_document` |
| finding canonical path | table `edges`; layer `document-canon`; kind `references_canonical` |
| finding severity/rule/message | table `diagnostics`; layer `document-canon` |
| inventory summary | table `metadata`; key `document_canon_inventory` |

Document canon findings are active structural cleanup evidence. Historical
records remain queryable graph nodes, but do not create diagnostics, warning
counts, or cleanup blockers. Neither class proves prose quality, citation
validity, code behavior, or merge readiness.

## Query Surface

Importing document-canon evidence into `prose_graph.sqlite` makes source
classification queryable by downstream report, source-packet, or cleanup tools.
This adapter only defines the import surface.

```text
source document path
  -> document-canon document_record
  -> active cleanup finding or historical record
  -> adapter action / reason payload
```

Callers that need reader-facing explanations own their own report wording and
review gates.
