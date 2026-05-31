<!--
@dependency-start
responsibility Defines the Prose Reasoning Graph DSL and graph contract.
upstream design README.md Prose Reasoning Graph canon directory index
upstream design ../../agents/workflows/workflow-references.md writing and discourse prior art
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current MVP implementation
downstream implementation ../../tests/agent_tools/test_prose_reasoning_graph.py validates current graph behavior
downstream design ../tools/prose_reasoning_graph.md documents CLI usage
downstream design ../../agents/skills/prose-reasoning-graph.md documents skill handoff workflow
downstream implementation ../../.agents/skills/prose-reasoning-graph/SKILL.md runtime skill entrypoint
downstream implementation ../../.claude/skills/prose-reasoning-graph/SKILL.md Claude-compatible skill entrypoint
@dependency-end
-->

# Prose Reasoning Graph DSL Specification

This document is the normative contract for the Prose Reasoning Graph DSL used
inside AgentCanon. The current implementation stores the graph in SQLite, but
the SQLite database is an intermediate analysis artifact. The durable source of
truth for vocabulary, layers, object shape, validation, and extension rules is
this specification.

The DSL represents prose as a typed, layered graph. A reader-facing order is a
projection from that graph, not the graph itself. This keeps discourse
relations, claims, evidence, experiment planning, edit operations, and natural
language explanations inspectable before an LLM or writing skill rewrites text.

## Normative Scope

This specification is binding for:

- graph layers and allowed MVP layer names;
- document, node, edge, diagnostic, edit operation, judgement, and metadata
  object fields;
- identifier conventions and source provenance requirements;
- projection and topological ordering rules;
- split, merge, bridge, and reorder operation packets;
- handoff boundaries to writing, review, experiment, and artifact skills;
- adapter rules for future code/design mirror inputs.

This specification does not define final prose quality, citation approval,
experiment acceptance, PR merge authority, or repository policy. Those
decisions remain with the receiving skill, reviewer, or workflow.

## Storage Boundary

The MVP persists graph data in SQLite because agents need durable intermediate
artifacts during a run. The database must not be treated as a durable authoring
source. A task may delete or regenerate a graph DB from the source document and
the same analysis profile.

Durable state consists of:

- the source prose, code, design document, or adapter input;
- this DSL specification;
- exported projection, diagnostics, explanation, integration plan, handoff,
  and rewrite packet artifacts when a workflow records them as evidence.

## Graph Object Model

### Document

A document object anchors one ingested source.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Stable document id inside one graph DB. |
| `path` | yes | Source path or adapter source locator. |
| `title` | yes | Human-readable title. |
| `kind` | yes | Source kind such as `document`, `markdown`, `plain-text`, or adapter kind. |
| `created_at` | yes | Graph ingestion timestamp. |

### Node

A node represents one typed item in one layer.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Graph-local stable id. |
| `document_id` | yes | Owning document id. |
| `layer` | yes | One layer from the MVP layer registry. |
| `kind` | yes | Layer-local node kind. |
| `label` | yes | Compact display label. |
| `text` | yes | Source text, generated explanation, or adapter text. |
| `source_start` | yes | Character offset in the source, or `0` for generated nodes. |
| `source_end` | yes | Character end offset in the source, or `0` for generated nodes. |
| `confidence` | yes | Floating-point confidence in `[0.0, 1.0]`. |
| `payload_json` | yes | JSON object for layer-specific fields. |

Nodes that derive from source text must preserve source offsets when the input
adapter can provide them. Generated metadata nodes must set offsets to `0` and
must record their generation basis in `payload_json`.

### Edge

An edge represents a typed relation between two nodes.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Graph-local stable id. |
| `layer` | yes | Layer that owns the relation. |
| `kind` | yes | Relation kind. |
| `from_node_id` | yes | Source node id. |
| `to_node_id` | yes | Target node id. |
| `order_kind` | yes | Ordering semantics such as `hard_before`, `adjacency_preferred`, or `none`. |
| `confidence` | yes | Floating-point confidence in `[0.0, 1.0]`. |
| `evidence_node_id` | no | Optional node supporting the relation. |
| `payload_json` | yes | JSON object for relation-specific fields. |

Edges may form a DAG for presentation and projection layers, but the whole
graph may contain cross-layer cycles. Projection algorithms must select the
ordering subgraph explicitly instead of assuming the entire graph is sortable.

### Diagnostic

A diagnostic records a graph-derived finding.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Stable diagnostic id. |
| `layer` | yes | Layer where the finding belongs. |
| `target_node_id` | no | Node target, or empty when document-level. |
| `target_edge_id` | no | Edge target, or empty when node/document-level. |
| `severity` | yes | `blocker`, `warn`, or `info`. |
| `rule` | yes | Stable rule id. |
| `message` | yes | Human-readable finding. |
| `suggested_action_json` | yes | JSON object with candidate next action. |

Diagnostics are advisory evidence. A workflow must not treat diagnostic absence
as proof that prose, logic, citation, experiment design, or code is correct.

### Edit Operation

An edit operation records a candidate transformation without mutating the
source.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Stable operation id. |
| `kind` | yes | Operation kind. |
| `target_ids_json` | yes | JSON array of target node ids. |
| `reason` | yes | Human-readable reason. |
| `payload_json` | yes | JSON object with preservation rules and operation hints. |

Every operation payload must include:

- `provenance`: where the operation was derived from;
- `history_effect`: whether the operation mutates source or only records a
  candidate.

The MVP uses `history_effect=records_candidate_without_mutating_source`.

### Judgement

A judgement records reviewer or tool judgement about a target.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Stable judgement id. |
| `target_type` | yes | `node`, `edge`, `diagnostic`, `operation`, or adapter target. |
| `target_id` | yes | Target id. |
| `source` | yes | Judgement source such as tool, reviewer, or skill. |
| `payload_json` | yes | JSON object with judgement fields. |
| `created_at` | yes | Judgement timestamp. |

The MVP schema reserves judgements for future workflow integration. A receiving
skill must not infer human approval from a generated judgement unless the
workflow explicitly records that authority.

## MVP Layer Registry

The MVP layer registry is closed. New first-class layers require an update to
this specification and the implementation. Adapter-specific experiments must
use payload fields or documented extension layers until promoted.

| Layer | Primary Nodes | Primary Edges | Responsibility |
| ----- | ------------- | ------------- | -------------- |
| `source` | source document | none | Preserve source identity and offsets. |
| `form` | section, paragraph, sentence | `contains` | Represent document form and source spans. |
| `concept` | term | `related_to` | Track repeated terms and concept adjacency. |
| `phase` | move | `realizes_move` | Label genre or rhetorical moves. |
| `discourse` | none in MVP | discourse relation edges | Represent paragraph-to-paragraph relations. |
| `argument` | claim | `stated_in` | Represent claims and their source sentence. |
| `evidence` | evidence | `supports` | Link evidence candidates to claims. |
| `experiment` | hypothesis, metric, baseline, experiment, expected result | none in MVP | Represent experiment-plan completeness. |
| `presentation` | none in MVP | `precedes` | Preserve or propose reader order. |
| `diagnostics` | none in MVP | none | Store findings over graph objects. |
| `edit-operation` | none in MVP | none | Store candidate split, merge, bridge, and reorder operations. |
| `explanation` | summary | none | Store generated natural-language explanation metadata. |
| `projection` | profile | none | Store projection profile and export metadata. |

## Identifier Conventions

Identifiers are graph-local and stable for one ingest/analyze run. They must be
compact enough for rewrite packets and human review.

| Pattern | Meaning |
| ------- | ------- |
| `source:document` | Source document node. |
| `section:<n>` | Markdown section node in source order. |
| `p:<n>` | Paragraph node in source order. |
| `s:<n>` | Sentence node in source order. |
| `concept:<n>` | Concept term node. |
| `phase:<n>` | Rhetorical move node aligned to paragraph order. |
| `claim:<n>` | Claim node. |
| `evidence:<n>` | Evidence node. |
| `experiment:<kind>:<n>` | Experiment layer node. |
| `projection:profile` | Projection metadata node. |
| `explanation:summary` | Explanation metadata node. |
| `diag:<rule>` | Document-level diagnostic. |
| `diag:<rule>:<target>` | Targeted diagnostic. |
| `op:<kind>:<targets>` | Edit operation id. |

External adapters must preserve their own stable source locator in payload
fields instead of replacing these graph-local ids with language-native ids.

## Relation Kinds

The MVP relation registry includes:

- `contains`: form containment, such as section to paragraph or paragraph to
  sentence.
- `precedes`: presentation order edge. A source-order edge uses
  `order_kind=hard_before`.
- `related_to`: concept co-occurrence or concept adjacency.
- `realizes_move`: paragraph realizes a phase or genre move.
- `elaborates`: next paragraph develops the previous material.
- `contrasts`: next paragraph contrasts or qualifies previous material.
- `causes`: next paragraph states cause, result, or inference.
- `exemplifies`: next paragraph gives an example.
- `limits`: next paragraph states limitation or risk.
- `stated_in`: claim is stated in a source sentence.
- `supports`: evidence supports a claim.

Relation payloads must explain the basis for inferred relations when the
relation was not directly encoded in the source.

## Projection And Ordering

A graph-to-text projection selects an ordering subgraph and emits a reader
sequence. A projection must not topologically sort the full layered graph.

Projection order must use this priority:

1. `presentation` edges with `order_kind=hard_before`.
1. Form containment from section to paragraph to sentence.
1. Requested profile constraints such as `writing`, `logic`, `experiment`,
   `report`, `academic`, `paper`, or `all`.
1. Phase preferences when the profile asks for genre move order.
1. Discourse edges with `order_kind=adjacency_preferred`.
1. Confidence score.
1. Source order as the final stable tie-breaker.

If the selected ordering subgraph has a cycle, the projection must record a
diagnostic instead of silently dropping edges. A reorder edit operation may
propose a priority topological sort, but the rewrite packet must preserve
source ids and explain which constraints were relaxed.

## Profiles And Skill Handoff

Profiles choose the receiving skill set and diagnostic emphasis.

| Profile | Primary Use | Handoff Targets |
| ------- | ----------- | --------------- |
| `writing` | Long-form paragraph and section flow. | `$long-form-writing`, `$structure-planning` |
| `logic` | Claim support and bridge triage. | `logic-gap-review`, `$academic-writing` |
| `experiment` | Experiment-plan completeness. | `$experiment-lifecycle`, `$report-writing` |
| `report` | Evidence traceability and report structure. | `$report-writing`, `$result-artifact-writeout` |
| `academic` | Scholarly logic and citation triage. | `$academic-writing`, `logic-gap-review`, `citation-evidence-review` |
| `paper` | Paper section and evidence review. | `$paper-writing`, `citation-evidence-review`, `logic-gap-review` |
| `all` | Full graph export and all current handoffs. | all registered prose graph handoff targets |

The handoff packet must include graph DB path, projection command,
diagnostics command, explanation command, and rewrite-plan command. The
receiving skill remains authoritative for its own review gate.

## Diagnostics Contract

Diagnostic rule ids are stable public contract. The MVP includes:

- `unsupported_claim`: a claim lacks a supporting evidence edge.
- `experiment_without_hypothesis`: experiment language appears without a
  hypothesis node.
- `experiment_without_metric`: experiment language appears without a metric
  node.
- `metric_without_baseline`: experiment planning lacks a baseline node.
- `experiment_without_expected_result`: experiment planning lacks an expected
  result node.
- `topic_jump_without_bridge`: adjacent paragraphs have low shared terms and no
  bridge cue.
- `claim_without_evidence_layer`: claims exist but no evidence nodes exist.
- `missing_layer_representation`: one or more required MVP layers has no
  representation.

New diagnostics must define severity, target type, triggering condition,
suggested action shape, and false-positive boundary in this directory before
they become stable workflow evidence.

## Edit Operation Contract

The MVP operation kinds are:

- `split_paragraph`: split one paragraph into smaller units.
- `merge_paragraphs`: integrate adjacent paragraphs with overlapping focus.
- `add_bridge`: add an explicit bridge between adjacent paragraphs.
- `reorder_paragraphs`: check reader order against presentation, phase, and
  discourse constraints.

Rewrite packets must include:

- operation id and kind;
- target ids;
- reason;
- preservation requirements;
- concrete change hints;
- explicit do-not rules.

Rewrite packets must not ask an LLM to invent new claims, change diagnostic
severity, or replace the receiving skill's review responsibility.

## Explanation Layer

The explanation layer converts graph evidence into natural language. It must
summarize:

- graph layer item count and profile;
- main claim path;
- discourse edges;
- gaps and diagnostics;
- recommended next edits;
- provenance and authority boundary.

The explanation is a reader-facing summary of graph state. It is not a
replacement for projection, diagnostics, or rewrite packets.

## Adapter Contract

Future independent-tool work may ingest code, design documents, shell scripts,
C++, Rust, or other structured sources. Adapters must map their source facts
into the same object model before adding new durable vocabulary.

An adapter must provide:

- `adapter_name` and `adapter_version` in graph metadata;
- source locator and language or format in document payload;
- stable source spans or symbolic locations when character spans are
  unavailable;
- graph-local ids following this spec;
- payload fields for native ids such as function name, shell command, C++
  symbol, Rust item, file path, or design clause;
- edges that use existing relation kinds when possible;
- diagnostics that distinguish source facts from inferred claims.

Code/design mirror checks must use explicit edges such as `implements`,
`tests`, `documents`, `constrains`, `contradicts`, `calls`, `imports`,
`includes`, `builds`, or `invokes` only after those relation kinds are added to
this specification or documented in an adapter-specific extension document.

Adapter experiments must not silently add first-class layers to the MVP layer
registry. Until promoted, adapter-specific layers must use an extension
namespace recorded in payload metadata and must not be required by general prose
workflows.

## Validation Requirements

A graph-producing implementation must validate:

- every node references an existing document;
- every edge references existing nodes;
- every object uses a registered layer or documented extension namespace;
- source-derived nodes carry provenance;
- generated nodes declare their generation basis;
- diagnostics use registered rule ids;
- edit operations include provenance and history effect;
- projections declare which ordering subgraph they use;
- handoff packets preserve receiving-skill authority boundaries.

Markdown or prose-only documentation changes that touch this specification
must run the repository Markdown checks and, when implementation headers change,
dependency-header checks. Implementation changes must also run the targeted
prose graph tests.
