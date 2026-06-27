<!--
@dependency-start
contract design
responsibility Defines the Graph DSL Core storage contract for structured analysis.
upstream design README.md structured analysis package index
upstream design ../dependency-manifest-design.md dependency manifest graph semantics
downstream design database-design.md SQLite materialization
downstream design ../prose-reasoning-graph/README.md documents prose adapter ownership
downstream design ../prose-reasoning-graph/dsl-spec.md prose adapter/profile over the core
downstream implementation ../../rust/agent-canon/src/structured_analysis.rs graph contract implementation
downstream design ../tools/prose_reasoning_graph.md documents the prose graph adapter command surface
downstream design ../tools/render_dependency_manifest_graph.md documents dependency graph projection rendering
@dependency-end
-->

# Graph DSL Core

This document is the storage contract for graph-shaped evidence in structured
analysis. It factors the common graph object model out of prose-specific,
dependency-specific, code-specific, report-specific, and proof-specific
surfaces.

The core boundary is storage, joins, projections, and representation checks.
Domain tools keep their own semantics and pass/fail authority as documented in `../prose-reasoning-graph/dsl-spec.md`,
`../dependency-manifest-design.md`, and
`../../rust/agent-canon/src/structured_analysis.rs`.

## Reader Map

Use this core contract to answer which graph storage objects are shared across
structured-analysis adapters and which semantics remain adapter-owned. Start
with the evidence ledger and mathematical contract, then read Core Object
Contract, Layer Registry, and Adapter Map for implementation details. The final
sections define validation, SQLite materialization, and extension rules.

## Evidence And Assumption Ledger

- Evidence paths:
  `README.md`, `database-design.md`,
  `../prose-reasoning-graph/dsl-spec.md`,
  `../dependency-manifest-design.md`, and
  `../../rust/agent-canon/src/structured_analysis.rs`.
- DSL term:
  Graph DSL Core means this storage contract plus the
  `structured-analysis graph-contract` validator path in
  `../../rust/agent-canon/src/structured_analysis.rs`.
- Assumption:
  SQLite files are regenerated artifacts. Source documents, adapter contracts,
  command outputs, and checker findings are durable authority.
- Assumption:
  Projection and operation families may be empty in a materialized DB. When
  present, they are represented by projection/edit-operation tables or by
  `projection` / `edit-operation` layer nodes.

## Mathematical Contract

Let an AgentCanon graph artifact be a tuple:

```text
G = (D, N, E, A, P, X, M)
```

where adapter profiles can demand non-empty families, and:

- `D` is a finite set of source documents or adapter source records.
- `N` is a finite set of typed nodes.
- `E` is a finite set of typed directed edges between nodes.
- `A` is a finite set of diagnostics, checks, and authority records over
  documents, nodes, edges, or adapter artifacts.
- `P` is a finite set of projection views derived from subgraphs of `N` and
  `E`.
- `X` is a finite set of candidate operations or reviewer/tool judgements.
- `M` is finite metadata describing graph version, adapter provenance,
  validation profile, and source artifact paths.

Each node and edge is qualified by `layer` and `kind`. The pair
`(layer, kind)` carries the local meaning recorded by
`../../rust/agent-canon/src/structured_analysis.rs`; adapter documents define
each layer's native semantics.

### Necessary

The object families above are necessary for AgentCanon graph storage:

- `D` is needed because source authority and regenerated artifacts are
  distinguished.
- `N` is needed because every adapter has entities: source spans, files,
  claims, findings, checks, functions, theorem nodes, or report sections.
- `E` is needed because every adapter has relations: containment, support,
  dependency, import/include, projection membership, proof consumption, or
  finding targets.
- `A` is needed because validation and review findings are first-class
  evidence rather than prose side comments.
- `P` is needed at the contract level because reader order, visualizations,
  report sections, and macro claims are derived views, not new source truth.
  A graph artifact that has no derived view materializes `P = empty`.
- `X` is needed at the contract level because rewrite, repair, proof, and
  review workflows need candidate actions without mutating source state. A
  graph artifact with no candidate action materializes `X = empty`.
- `M` is needed because graph artifacts are regenerated and carry version,
  command, source, and adapter provenance.

Dropping any one family forces at least one existing surface to encode its
state ad hoc in another family: for example, dropping `P` turns derived views
into source nodes, while dropping `A` turns checker findings into unstructured
prose.

### Sufficient

The tuple is sufficient for current AgentCanon graph-shaped surfaces with a
faithful adapter mapping such as the mappings in
`../prose-reasoning-graph/dsl-spec.md` and
`../dependency-manifest-design.md`:

```text
phi_surface : SurfaceObject -> D + N + E + A + P + X + M
```

such that:

1. Native source identity is recoverable from `D` plus `payload_json`.
2. Native entity identity is recoverable from node `id`, `layer`, `kind`, and
   `payload_json`.
3. Native relation identity is recoverable from edge `id`, `layer`, `kind`,
   endpoints, and `payload_json`.
4. Adapter-specific authority is recoverable from diagnostics, checks, or
   metadata rather than inferred from projection shape.
5. Every projection records its member node/edge ids and inference basis.

Under these conditions, two graph artifacts are representation-equivalent for a
workflow profile when they have the same source records, the same layer-kind
qualified node and edge facts, the same authority records, and projections that
derive from the same member subgraphs. They may differ in SQLite file name,
row order, generated ids that preserve payload source locators, or rendering
format.

This is a storage and projection equivalence. It is not a mathematical proof of
claims, citation support, dependency validity, runtime correctness, or PR
readiness.

## Core Object Contract

### Source Record

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable source record id. |
| `path` | yes | Repo path, URI, or adapter source locator. |
| `title` | yes | Human-readable label. |
| `kind` | yes | Source family such as `markdown`, `code`, `artifact`, `report`, or `adapter`. |
| `created_at` | yes | Materialization timestamp. |

### Node Record

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Graph-local stable id. |
| `document_id` | yes | Owning source record id. |
| `layer` | yes | Layer registry entry or adapter namespace. |
| `kind` | yes | Layer-local node kind. |
| `label` | yes | Compact display label. |
| `text` | yes | Source text, generated text, or adapter summary. |
| `source_start` | yes | Character start offset, or `0` for generated/adapter nodes. |
| `source_end` | yes | Character end offset, or `0` for generated/adapter nodes. |
| `confidence` | yes | Confidence-like value in `[0.0, 1.0]`. |
| `payload_json` | yes | JSON object with native locators, provenance, authority, and adapter fields. |

Source-derived nodes record source locator and segmentation basis in
`payload_json` when offsets alone are insufficient. Generated nodes record
generation basis.

### Edge Record

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Graph-local stable id. |
| `layer` | yes | Layer for relation meaning. |
| `kind` | yes | Layer-local relation kind. |
| `from_node_id` | yes | Source endpoint. |
| `to_node_id` | yes | Target endpoint. |
| `order_kind` | yes | `hard_before`, `adjacency_preferred`, `none`, or adapter-local equivalent. |
| `confidence` | yes | Confidence-like value in `[0.0, 1.0]`. |
| `evidence_node_id` | no | Optional node that supports the edge. |
| `payload_json` | yes | JSON object with native relation locator, basis, and provenance. |

Edge meaning is always `layer + kind`. A dependency manifest edge, code import,
proof-consumes edge, and prose support edge can share a storage shape while
keeping distinct semantics.

### Diagnostic Or Check Record

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable diagnostic or check id. |
| `layer` | yes | Layer where the finding belongs. |
| `target_node_id` | yes | Target node id or empty string. |
| `target_edge_id` | yes | Target edge id or empty string. |
| `severity` | yes | `blocker`, `warn`, or `info`. |
| `rule` | yes | Stable rule id. |
| `message` | yes | Human-readable finding. |
| `suggested_action_json` | yes | JSON object with verification route, repair command, or next evidence. |

### Projection View

A projection view is stored either as dedicated projection tables or as
projection-layer nodes and membership edges. In either representation it carries:

- projection id;
- profile;
- role;
- ordered member node/edge ids;
- inference basis;
- authority boundary;
- recommended rendering form when applicable.

Projection views are regenerated from source graph facts. They do not become
additional source records.

### Operation Or Judgement

The operation/judgement family is part of the core contract. A graph artifact
may materialize it as an empty set. When present, records capture a candidate
source edit, repair step, proof step, review classification, or tool judgement.
They carry target ids, source, status, and `payload_json`.

## Layer Registry

The core recognizes these durable layer names:

| Layer | Owner |
| --- | --- |
| `source` | Source identity and spans. |
| `form` | Text form: section, paragraph, sentence, EDU. |
| `prose` | Prose adapter profile when a single umbrella layer is needed. |
| `concept` | Derived terms and concept adjacency. |
| `discourse` | Discourse relations. |
| `argument` | Claims, warrants, conclusions. |
| `evidence` | Evidence objects and support links. |
| `presentation` | Reader order and rendering recommendations. |
| `projection` | Derived views and export profiles. |
| `diagnostics` | Findings and validation queue. |
| `edit-operation` | Candidate rewrite/repair operations. |
| `artifact` | Git-visible files, directories, and directory responsibility. |
| `document-canon` | Document inventory and cleanup findings. |
| `deps` | Dependency manifest graph adapter. |
| `code` | Language import/include/source relation adapter. |
| `report` | Report claim/evidence/finding/action trace. |
| `algorithm` | Algorithm expansion or flow graph adapter. |
| `proof` | Lemma/theorem/proof-status graph adapter. |

Adapter experiments can start with an adapter namespace layer or payload fields until a
layer is promoted here.

## Adapter Map

| Surface | Mapping |
| --- | --- |
| Prose Reasoning Graph | Source spans correspond to `source`/`form`; claims, evidence, discourse, presentation features, diagnostics, edit operations, and projections correspond to their matching layers in `../prose-reasoning-graph/dsl-spec.md`. |
| Dependency manifest graph | Manifest records correspond to `deps` nodes and edges; dependency validation findings correspond to diagnostics/check records in `../dependency-manifest-design.md`. |
| Code dependency graph | Source files and symbols correspond to `code` nodes or payload locators; imports/includes/source references correspond to `code` edges. |
| Artifact and directory responsibility | Files/directories correspond to `artifact` nodes; containment and responsibility support correspond to `artifact` edges in `../../rust/agent-canon/src/structured_analysis.rs`. |
| Document canon | Inventory rows and findings correspond to document-canon layer nodes, edges, and diagnostics in `../../rust/agent-canon/src/structured_analysis.rs`. |
| Report contract | Reports, sections, claims, evidence refs, findings, actions, and check runs correspond to `report` layer objects in `../../rust/agent-canon/src/structured_analysis.rs`. |
| Algorithm/proof graphs | Algorithm steps, recurrence facts, theorem nodes, proof dependencies, and proof status correspond to `algorithm` and `proof` layers while retaining checker/proof authority outside the storage core. |

## Validation Contract

The deterministic validator in
`../../rust/agent-canon/src/structured_analysis.rs` checks representation
shape. The current SQLite materialization covers the materialized tables
`documents`, `nodes`, `edges`, `diagnostics`, and `metadata`; projection and
operation families are checked when a DB materializes them as projection/edit-
operation tables or as projection/edit-operation layer nodes.

- required tables or exported object families are present;
- required fields exist;
- `payload_json` and action payloads parse as JSON objects;
- node layers are registered or adapter-namespaced;
- node `document_id` resolves when the graph claims a document table;
- edge endpoints resolve to existing nodes;
- diagnostic targets resolve when populated;
- severity and order fields follow known values or adapter-local payload evidence;
- projections retain member ids and inference basis when projection tables or
  projection nodes are present.

Graph-contract diagnostics are emitted by
`../../rust/agent-canon/src/structured_analysis.rs`. Semantic checks stay with
the owning adapter:

- dependency graph validity remains with dependency manifest tools;
- code correctness remains with language checkers/build/tests;
- prose quality remains with prose graph diagnostics and reviewers;
- citation and proof status remain with citation/proof workflows;
- PR readiness remains with the workflow closeout gates.

## SQLite Materialization

The current Rust structured-analysis implementation materializes the core with:

- `documents`
- `nodes`
- `edges`
- `diagnostics`
- `metadata`

Dedicated attached databases or projection-specific tables may add richer
storage. They remain faithful to this object contract by keeping stable ids,
layer-qualified semantics, source/provenance payloads, and authority records.

## Extension Rule

Add a new layer or adapter mapping only when an existing surface cannot be
faithfully represented by current layer-kind pairs plus `payload_json`.
Renderer choices, CLI conveniences, and report layout preferences are
projection profiles rather than new storage layers.
