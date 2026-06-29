<!--
@dependency-start
contract design
responsibility Defines SQLite database design for structured prose, report, and dependency analysis.
upstream design README.md structured analysis package index
upstream design graph-dsl.md Graph DSL Core storage contract
upstream design ../prose-reasoning-graph/dsl-spec.md prose graph DSL and projection contract
upstream design ../dependency-manifest-design.md dependency manifest DSL and validation model
upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current prose graph SQLite implementation
upstream implementation ../../rust/agent-canon/src/structured_analysis.rs Rust structured-analysis CLI implementation
upstream implementation ../../tools/agent_tools/check_dependency_graph.sh emits dependency manifest graph artifacts
downstream design dependency-header-analysis.md maps dependency header graph data into this DB model
downstream design code-analysis.md maps code dependency evidence into this DB model
downstream design document-canon-analysis.md maps duplicate and non-canonical document evidence into this DB model
@dependency-end
-->

# Structured Analysis Database Design

This document is the SQLite materialization contract implemented by
`../../rust/agent-canon/src/structured_analysis.rs`. Broader prose, dependency,
report, and corpus adapters keep their contracts through `prose_reasoning_graph.py`.
This file records the shared Graph DSL Core storage created and validated by
`initialize_graph_schema` and
`validate_graph_contract`.

## Reader Map

- Owns the SQLite materialization contract for structured prose, report, and
  dependency analysis.
- Main path: Evidence And Assumption Ledger, Storage Boundary, Core Tables,
  Implemented Layers, Validation Contract, and Build Flow.
- Read this before changing structured-analysis DB tables, cache artifacts, or
  adapter-to-storage mappings.
- Boundary: adapter vocabulary stays with the adapter docs; this file defines
  shared storage shape and validation.

## Evidence And Assumption Ledger

- Evidence sources:
  `graph-dsl.md`, `../prose-reasoning-graph/dsl-spec.md`,
  `../dependency-manifest-design.md`, and
  `../../rust/agent-canon/src/structured_analysis.rs`.
- Assumption:
  `agent-canon structured-analysis build` keeps regenerated SQLite DB files in
  the structured-analysis cache. `--out-dir` names a durable report export
  directory for JSON/Markdown evidence and summary files.
- Parent-doc alignment:
  `graph-dsl.md` owns the necessary/sufficient graph object family contract.
  This document maps that core through `initialize_graph_schema` to `metadata`,
  `documents`, `nodes`, `edges`, and `diagnostics`.
- Profile coverage boundary:
  Prose DSL terms such as source-truth anchor / source span, lower graph /
  lower text unit, typed relation, projection view / derived projection,
  reader-state, and macro-claim remain adapter-level vocabulary. The shared DB
  stores adapter-emitted terms through layer/kind values and `payload_json`.
- Refactor handoff:
  Run bundles keep `document_inventory.json`,
  `exports/document_inventory.md`, `structured_analysis_build.json`, and
  `exports/structured_analysis_summary.md`. The DB paths are emitted as command
  output fields.

## Storage Boundary

`agent-canon structured-analysis build --root <repo>` materializes the shared
core into these cache files:

```text
${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}/
  <repo-id>/<profile>-current/
    prose_graph.sqlite
    diagnostics.sqlite
```

`--out-dir <report-dir>` changes the durable report export path:

```text
<report-dir>/
  document_inventory.json
  structured_analysis_build.json
  exports/document_inventory.md
  exports/structured_analysis_summary.md
```

The report directory is the durable export surface for `document_inventory.json`
and `structured_analysis_build.json`. The user-home cache keeps normal SQLite
locking and journaling. `structured_analysis_build.json` is compact run-bundle
evidence.

## Core Tables

The implemented `prose_graph.sqlite` schema has five required tables:

| Table | Key columns | Graph family |
| --- | --- | --- |
| `metadata` | `key`, `value` | `M` metadata. |
| `documents` | `id`, `path`, `title`, `kind`, `created_at` | `D` source records. |
| `nodes` | `id`, `document_id`, `layer`, `kind`, `label`, `text`, `source_start`, `source_end`, `confidence`, `payload_json` | `N` typed node records in the nodes table. |
| `edges` | `id`, `layer`, `kind`, `from_node_id`, `to_node_id`, `order_kind`, `confidence`, `evidence_node_id`, `payload_json` | `E` typed directed edge records in the edges table. |
| `diagnostics` | `id`, `layer`, `target_node_id`, `target_edge_id`, `severity`, `rule`, `message`, `suggested_action_json` | `A` diagnostics. |

Projection and operation families from `graph-dsl.md` use `nodes` or `edges`
rows when an adapter emits them through `payload_json`. Empty projection or
operation row sets conform to the core storage contract.

## Implemented Layers

`structured_analysis.rs` currently writes these layers:

| Layer | Rows | Source |
| --- | --- | --- |
| `artifact` | directory/file nodes, containment edges, directory responsibility nodes, responsibility edges, and directory-coverage diagnostics. | `collect_files`, dependency manifest responsibility lines, and README paths. |
| `document-canon` | document inventory nodes, active finding nodes, historical-record nodes, and finding-target edges. | `document_inventory.json` generated by `document-inventory`. |

The `diagnostics.sqlite` file is a warning snapshot derived from the source DB.
`prose_graph.sqlite` remains the source graph for
`analyze_structured_analysis_db`, closeout, and dashboard use.

## Validation Contract

`agent-canon structured-analysis graph-contract --db <prose_graph.sqlite>`
checks the shared schema:

- required table existence for `metadata`, `documents`, `nodes`, `edges`, and
  `diagnostics`;
- required column existence for every core table;
- JSON shape for `payload_json` and `suggested_action_json`;
- endpoint existence for `from_node_id`, `to_node_id`, and
  `evidence_node_id`;
- known layer, known ordering, confidence range, and diagnostic severity rules.

Adapter-specific semantics stay outside this command. For example,
dependency-header pass/fail remains with `check_dependency_graph.sh`, and prose
rewrite semantics remain with `prose_reasoning_graph.py`.

## Build Flow

1. `build_report` creates document inventory data from the git-visible tree.
2. Report artifacts are written to `report_dir`.
3. `prose_graph.sqlite` and `diagnostics.sqlite` are recreated under
   `cache_dir`.
4. `initialize_graph_schema` creates the five core tables.
5. `import_inventory_payload` imports the `document-canon` layer.
6. `import_artifact_layer` imports the `artifact` layer.
7. `analyze_structured_analysis_db` writes warning summary rows.
8. `write_build_artifacts` writes durable JSON/Markdown build summaries to
   `report_dir`.

The DB files are regenerated artifacts. The durable authority is the source
tree, dependency manifests, adapter docs, command output, and report exports.
