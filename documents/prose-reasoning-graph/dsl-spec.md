<!--
@dependency-start
contract reference
responsibility Defines the Prose Reasoning Graph DSL and graph contract.
upstream design README.md Prose Reasoning Graph canon directory index
upstream design ../structured-analysis/graph-dsl.md shared Graph DSL Core storage contract
upstream design ../../agents/workflows/workflow-references.md writing and discourse prior art
coverage dsl_design_trace requires source-truth anchor|source truth|source span; lower graph|lower text unit; typed relation; projection view|derived projection|reader-state|macro-claim
coverage graph_format_trace requires node record|nodes table; edge record|edges table; payload_json|payload json
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current MVP implementation
downstream implementation ../../tests/agent_tools/test_prose_reasoning_graph.py validates current graph behavior
downstream design ../tools/prose_reasoning_graph.md documents CLI usage
downstream design ../tools/README.md documents graph visualization tool routing from the documentation hub
downstream design ../tools/render_dependency_manifest_graph.md documents dependency graph visualization adapter
downstream design ../tools/semantic_provider_html_report.md documents semantic provider visualization adapter
downstream design ../tools/jit_canonical_ir.md documents JIT-canonical source facts available to future graph visualization adapters
downstream design ../../tools/README.md documents graph visualization tool routing from the execution hub
downstream design ../../agents/skills/prose-reasoning-graph.md documents skill handoff workflow
downstream implementation ../../.agents/skills/prose-reasoning-graph/SKILL.md runtime skill entrypoint
@dependency-end
-->

# Prose Reasoning Graph DSL Specification

This document is the prose adapter/profile contract over the shared
[Graph DSL Core](../structured-analysis/graph-dsl.md). The current implementation
stores the graph in SQLite, but the SQLite database is an intermediate analysis
artifact. The durable source of truth for prose vocabulary, prose layers,
projection rules, validation, and extension rules is this specification.
Generic storage object families and cross-adapter contract validation are owned
by Graph DSL Core.

The DSL represents prose as a typed, layered graph. A reader-facing order is a
projection from that graph, not the graph itself. This keeps discourse
relations, claims, evidence, experiment planning, edit operations, and natural
language explanations inspectable before an LLM or writing skill rewrites text.

The canonical graph is a text-anchored semantic graph: prose content is anchored
in source text units, normally sentences or elementary discourse units (EDUs),
and semantic, discourse, argument, experiment, and presentation relations are
typed edges anchored to those text units. Macro-claims, rhetorical moves,
reader-state transitions, subtopics, and argument blocks are projection views
over that same graph. The durable boundary is canonical graph versus projection
view, not one prose layer versus another.

## Reader Map

Use this specification to answer what the prose graph DSL owns, which graph
objects and relation vocabulary are valid, and how projections, diagnostics,
edit operations, explanations, adapters, and validation fit together. Start
with Normative Scope, Linguistic Grounding, and the responsibility contracts for
authority boundaries; then read the object model, layer registry, identifiers,
relation kinds, and projection sections for implementation work. The final
sections cover visualization, handoff profiles, verification routes,
diagnostics, edit packets, explanation, adapter behavior, and validation.

## Normative Scope

This specification is binding for:

- prose graph layers and allowed prose MVP layer names;
- graph visualization adapters and projection artifacts;
- document responsibility contracts and responsibility-derived coverage checks;
- directory responsibility projections derived from README and child artifact
  responsibility evidence;
- document, node, edge, diagnostic, edit operation, judgement, and metadata
  object fields;
- identifier conventions and source provenance requirements;
- projection and topological ordering rules;
- split, merge, bridge, and reorder operation packets;
- handoff boundaries to writing, review, experiment, and artifact skills;
- adapter rules for future code/design mirror inputs that enter prose analysis.

This specification does not define generic graph storage, final prose quality,
citation approval, experiment acceptance, PR merge authority, or repository
policy. Generic storage belongs to Graph DSL Core. Other decisions remain with
the receiving skill, reviewer, or workflow.

## Linguistic Grounding

The DSL intentionally borrows constraints from several discourse traditions
without implementing any one of them wholesale:

- Annotation Graphs and LAF-style annotation motivate source anchoring with
  multiple typed annotation layers over the same text.
- RST motivates relations over text spans and the distinction between local
  realization and higher text organization.
- PDTB motivates discourse relations with text-span arguments, sense labels,
  attribution, and connective evidence.
- RST dependency views and eRST motivate graph-shaped discourse overlays rather
  than treating macro constituency spans as primitive source objects.
- SDRT motivates graph-shaped discourse interpretation and consistency
  constraints over discourse segments.
- Centering theory motivates local reader-attention and coherence state
  transitions.
- Kintsch and van Dijk style macrostructure theory motivates deriving a gist or
  macrostructure view from detailed text meaning.
- TextTiling motivates derived passage or subtopic segmentation from source text
  evidence.
- Argumentative Zoning motivates scholarly rhetorical-status labels as derived
  projections over sentence or span anchors.

These sources justify a text-anchored canonical graph plus projection-view
design. They do not authorize a single scalar prose-quality score, a full
RST/SDRT parser, or a sequential pipeline where early macro labels become
unquestioned truth.

## Storage Boundary

The MVP persists graph data in SQLite because agents need durable intermediate
artifacts during a run. The database must not be treated as a durable authoring
source. A task may delete or regenerate a graph DB from the source document and
the same analysis profile.

DB creation commands default to
`${AGENT_CANON_PROSE_GRAPH_HOME:-$HOME/.cache/agent-canon/prose-reasoning-graph}`;
callers may pass `--db <path>` only when an explicit artifact location is
needed.

Durable state consists of:

- the source prose, code, design document, or adapter input;
- this DSL specification;
- exported projection, diagnostics, explanation, integration plan, handoff, and
  rewrite packet artifacts when a workflow records them as evidence.

Tool stdout is not a durable graph surface. Full graph, projection,
diagnostic, explanation, handoff, and rewrite packet structures must be written
to DB-backed or file artifacts; stdout should contain only compact status,
counts, and artifact paths so agents do not spend context on raw structures.

The graph database may materialize derived analysis objects for convenience, but
source-truth must remain recoverable from source text anchors and source spans.
Projection artifacts may be regenerated with a new projection profile without
rewriting the source document.

## Document Responsibility Contract

Each repository document may declare its responsibility in the top dependency
manifest. Responsibility validation is a `document-canon` layer in the
structured graph. The Rust `agent-canon structured-analysis document-inventory`
command reads the declared responsibility and upstream design trace, then emits
generic `document_responsibility_gap` findings when the document does not cover
the source surface it claims as part of its stated job. The Python
`prose_reasoning_graph.py` parser does not create this layer directly, but
workflows materialize the findings in the same structured graph DB before
diagnostic integration.

When structured-analysis imports those findings into a graph DB, they
materialize under the `document-canon` layer as diagnostics and finding nodes.
They participate in the same diagnostic, integration, verification, and rewrite
loop as prose-source diagnostics.
The checker must not use superficial predicates such as named-heading presence
or visual-block presence as standalone warning conditions. A downstream
document is checked when it cites an upstream design document that declares
coverage rules; no Rust-side path, section-name, figure, or responsibility-word
case list decides the rule.

Design documents may declare reusable coverage rules in their dependency
manifest with `coverage <id> requires <term group>; <term group>`. Each term
group is satisfied when at least one `|`-separated alternative appears in the
downstream document that cites the design as `upstream design`. This keeps
responsibility validation generic: the checker reads the design document's
declared coverage rules instead of hard-coding path-specific cases. Missing
coverage is recorded in the finding reason, for example
`missing_responsibility_coverage=dsl_design_trace` or
`missing_responsibility_coverage=graph_format_trace`, while the finding kind
remains `document_responsibility_gap`.

A `document_responsibility_gap` diagnostic must set
`suggested_action_json.verification_route` to
`document_responsibility_verification`. The route metadata must identify the
downstream path, upstream design path, missing coverage reason, required
evidence, and recursive verification steps. The checker records the route and
the missing coverage groups; the skill loop owns expansion into child
questions, downstream span selection, rewrite packet creation, and rerunning the
same checker until the gap is closed, explicitly limited, or preserved as an
unresolved finding.

## Directory Responsibility Contract

Directory responsibility is a derived projection over repository artifact and
document structure. A directory node is not itself prose source truth. The
structured-analysis adapter derives a `directory_responsibility` node from, in
priority order, the directory `README.md` dependency-manifest responsibility,
the `README.md` title, descendant artifact dependency-manifest
responsibilities, or a path-only alternate route.

The projection must preserve evidence edges. The directory node connects to the
derived responsibility node with `has_responsibility`; README and child
artifact nodes that support the projection connect to the responsibility node
with `supports`. The responsibility node payload records `basis`,
`readme_path`, `evidence_paths`, descendant counts, child kind counts, and
whether the projection came from document structure.

When a directory README exists but its declared responsibility has low lexical
coverage of child artifact responsibilities, structured-analysis emits
`directory_responsibility_low_child_coverage` on the `artifact` layer. The
diagnostic is advisory. Its verification route is
`directory_responsibility_verification`, which asks the skill loop to identify
the missing child responsibilities, choose the README paragraph or dependency
manifest line that should carry the directory responsibility, and rerun
structured-analysis after any rewrite.

This contract extends document responsibility checks without replacing them.
Document responsibility verifies whether one document covers declared upstream
design coverage. Directory responsibility verifies whether a directory-level
projection covers the responsibilities of child documents and code artifacts.

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

A node represents one typed item in one layer. The current MVP implementation
materializes source, form, concept, phase, discourse, argument, evidence,
experiment, presentation, explanation, projection, artifact, and document-canon
nodes. The canonical semantic graph contract classifies these nodes by
authority:

- text-bearing `form` nodes are source-truth nodes for prose content;
- `section` and `paragraph` nodes are source form containers and reader-order
  anchors, not derived macro-claims;
- `sentence` and future `edu` nodes are the smallest default authoring anchors;
- non-form analysis nodes such as `claim`, `evidence`, `phase`, `concept`, and
  `experiment` are derived analysis conveniences unless their payload declares
  source spans and member anchor ids.
- `artifact` layer nodes such as `directory`, `file`, and
  `directory_responsibility` are repository-structure projections. They are
  derived from git-visible files, dependency manifests, and README structure;
  they are not final ownership decisions.

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

The current MVP stores simpler payloads for existing form nodes. Future
canonical-span implementations must add these anchor payload fields for every
source-truth prose node they create or rewrite:

- `span_kind`: `sentence`, `edu`, `paragraph`, `section`, or adapter-specific
  documented span kind;
- `source_locator`: path, URI, or adapter locator for the source span;
- `segmentation_basis`: tool, parser, reviewer, or adapter rule that produced
  the boundary.

### Derived View Object

A derived view object represents a macro prose unit inferred from a canonical
graph subgraph. It is a normative target for the projection-view model, not a
current MVP export. A workflow may export it in projection JSON/YAML or store it
in a projection table, but it must be explicitly marked as derived and must not
be treated as an additional source node.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Projection-local id such as `view:<profile>:<n>`. |
| `profile` | yes | Projection profile that created the view. |
| `members_json` | yes | Ordered canonical node ids included in the view. |
| `role` | yes | Inferred role such as `setup`, `claim`, `warrant`, `evidence`, `implication`, `plan`, or `conclusion`. |
| `reader_state_before` | no | Compact inferred reader-state input. |
| `reader_state_after` | no | Compact inferred reader-state output. |
| `abstraction_level` | no | `surface`, `example`, `operational`, `conceptual`, or `meta`. |
| `recommended_format` | no | Reader-facing form recommendation: `prose`, `bulleted_list`, `ordered_list`, `table`, `figure`, or `equation`. |
| `format_reason` | no | Short reason grounded in graph structure, role, or source cues. |
| `inference_basis_json` | yes | Edges, diagnostics, rules, or reviewer judgements used to create the view. |
| `confidence` | yes | Floating-point confidence in `[0.0, 1.0]`. |

When implemented, derived views must be invalidated or regenerated when any
member canonical node, ordering edge, or inference-basis edge changes. They must
not be edited as if they were source prose.

### Corpus Hint Object

A corpus hint object records the academic or domain corpus that should calibrate
analysis, retrieval, examples, and evaluation. In the MVP, corpus management is
a LocalLLM IR extraction task: `agent-canon local-llm extract-prose-ir` receives
the source documents, user prompt, and optional terms, splits them into bounded
parts, and returns merged `corpus_hints`. User-prompt context is allowed because
the user often names the intended field before the draft itself contains
field-specific vocabulary.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `corpus_id` | yes | Stable corpus/profile id, such as `academic_writing`, `software_engineering`, `experimental_report`, or `formal_reasoning`. |
| `label` | yes | Human-readable corpus label. |
| `score` | yes | LocalLLM IR ranking score or confidence-like ordering value. |
| `basis` | yes | LocalLLM IR extraction basis, including signal terms, source path, prompt context indicator, or explicit workflow setting. |
| `selected` | yes | Whether this hint is the current default corpus for downstream analysis. |

Corpus hints are calibration metadata, not evidence. A downstream literature
search, evaluator, or reviewer may use them to choose examples and norms, but
must still cite or inspect actual sources before making scholarly claims.

### Edge

An edge represents a typed relation between two prose-profile nodes. The shared
storage shape is defined by Graph DSL Core; this section constrains prose
relation meaning and projection use.

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

Edges that express dependency, support, prerequisite, refinement,
generalization, conclusion, or presentation order form the selected ordering DAG
for a projection profile. The whole graph may contain cross-layer cycles because
contrast, coreference, equivalence, and diagnostic references are not ordering
constraints. Projection algorithms must select the ordering subgraph explicitly
instead of assuming the entire graph is sortable.

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

## MVP Prose Layer Registry

The prose MVP layer registry is closed for prose-profile semantics. New
first-class shared layers require an update to Graph DSL Core. New
prose-specific layer meanings require an update to this specification and the
implementation. Adapter-specific experiments use payload fields or documented
extension layers until promoted. The registry distinguishes source-truth layers
from derived analysis and projection layers.

| Layer | Primary Nodes | Primary Edges | Responsibility |
| ----- | ------------- | ------------- | -------------- |
| `source` | source document | none | Preserve source identity and offsets. |
| `form` | section, paragraph, sentence, edu | `contains` | Represent document form and source spans. |
| `concept` | term | `related_to` | Track repeated terms and concept adjacency as derived analysis. |
| `phase` | move | `realizes_move` | Label genre or rhetorical moves as derived analysis. |
| `discourse` | none in MVP | discourse relation edges | Represent paragraph-to-paragraph relations. |
| `argument` | claim | `stated_in` | Represent derived claim views and their source sentence or EDU anchors. |
| `evidence` | evidence, document_responsibility, dependency_manifest | `supports` | Link source evidence and dependency-manifest responsibility evidence to claim views. |
| `experiment` | hypothesis, metric, baseline, experiment, expected result | none in MVP | Represent derived experiment-plan completeness. |
| `presentation` | none in MVP | `precedes` | Preserve or propose reader order. |
| `diagnostics` | none in MVP | none | Store findings over graph objects. |
| `edit-operation` | none in MVP | none | Store candidate split, merge, bridge, and reorder operations. |
| `explanation` | summary | none | Store generated natural-language explanation metadata. |
| `projection` | profile | none | Store projection profile and export metadata. |
| `artifact` | directory, file, directory_responsibility | contains, explains_directory, has_responsibility, supports | Store repository-structure projections derived from git-visible files and dependency manifests. |
| `document-canon` | document_record, finding | targets_document, references_canonical | Store document inventory and cleanup evidence. |

Only `source` and text-bearing `form` nodes are canonical source-truth for prose
content. `section` and `paragraph` are source form containers; they are not the
same thing as derived macro prose units such as subtopics, macro-claims, or
argument blocks. Other layer nodes are derived analysis conveniences unless
their payload explicitly declares source spans and member anchor ids.

Dependency manifests are generic evidence inputs, not document-type exceptions.
The graph may materialize `responsibility`, `upstream`, and `downstream`
dependency-manifest records as `evidence` layer nodes. A claim is supported when
the lower graph can connect it to source evidence or to dependency-manifest
responsibility evidence through a `supports` edge. `unsupported_claim` is emitted
only when that support edge is absent.

## Identifier Conventions

Identifiers are graph-local and stable for one ingest/analyze run. They must be
compact enough for rewrite packets and human review.

| Pattern | Meaning |
| ------- | ------- |
| `source:document` | Source document node. |
| `section:<n>` | Markdown section node in source order. |
| `p:<n>` | Paragraph node in source order. |
| `s:<n>` | Sentence node in source order. |
| `edu:<n>` | Elementary discourse unit in source order. |
| `concept:<n>` | Concept term node. |
| `phase:<n>` | Rhetorical move node aligned to paragraph order. |
| `claim:<n>` | Claim node. |
| `evidence:<n>` | Evidence node. |
| `experiment:<kind>:<n>` | Experiment layer node. |
| `projection:profile` | Projection metadata node. |
| `explanation:summary` | Explanation metadata node. |
| `view:<profile>:<n>` | Derived projection-view id in exported projections. |
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
- `requires`: one text unit requires a prior premise, definition, condition,
  or reader-state update.
- `refines`: one text unit specializes, qualifies, or operationalizes another.
- `generalizes`: one text unit abstracts from examples, evidence, or local
  observations.
- `concludes`: one text unit states a conclusion or decision that depends on
  earlier units.
- `elaborates`: next paragraph develops the previous material.
- `contrasts`: next paragraph contrasts or qualifies previous material.
- `causes`: next paragraph states cause, result, or inference.
- `exemplifies`: next paragraph gives an example.
- `limits`: next paragraph states limitation or risk.
- `stated_in`: claim is stated in a source sentence.
- `supports`: evidence supports a claim.
- `explains_directory`: README file describes its parent directory.
- `has_responsibility`: directory node points to a derived
  `directory_responsibility` projection node.
- `targets_document`: document-canon finding points to the affected document
  record.
- `references_canonical`: document-canon finding points to the likely
  canonical document record.

Relation payloads must explain the basis for inferred relations when the
relation was not directly encoded in the source.

Relations used for projection ordering must state whether they participate in
the selected ordering DAG. Symmetric or non-ordering relations such as contrast,
coreference, paraphrase, and equivalence must use `order_kind=none` unless a
profile-specific projection explicitly promotes them to an ordering constraint.

## Canonical Graph And Projection Views

The canonical graph is the analysis substrate for prose. It contains
text-anchored source units and typed semantic, discourse, argument, experiment,
and presentation relations among them. A projection may select an ordering DAG
from that graph for dependency-like relations, while non-ordering overlays
remain normal typed edges.

Required canonical graph invariants:

- every source-truth prose node carries actual source text and provenance;
- sentence and EDU nodes are the smallest default authoring anchors;
- paragraph and section nodes are containers and reader-order anchors;
- dependency-like relation subgraphs must either be acyclic or report strongly
  connected components as diagnostics before projection;
- inferred relation edges must include basis and confidence;
- missing implicit premises, warrants, definitions, baselines, or reader-state
  steps must be diagnostics, not invented source nodes.

Macro prose structure is derived through projection. A projection may contract a
connected canonical subgraph into a view, assign a role, and describe reader
state or abstraction-level movement. It must retain the member canonical node
ids so an agent can return to the source text.

Projection may also recommend a non-prose presentation form from a materialized
presentation feature subgraph, not from a fixed section-title, raw-word
checklist, or numeric threshold. Bulleted lists fit a `parallel_sibling_set`
feature, ordered lists fit a `dependency_sequence` feature, tables fit an
`aligned_attribute_set` feature, figures fit a `relational_topology` feature,
and equations fit a `formal_constraint` feature. These recommendations are
presentation views over canonical anchors, not source-truth replacements. A
renderer or LLM rewrite pass may accept, reject, or combine them, but must
preserve provenance back to the member anchors.

The feature subgraph is part of the `presentation` layer. A source anchor points
to a `presentation` / `feature` node with a `has_feature` edge. The feature node
records `feature_kind`, `source_anchor_id`, `member_anchor_ids`, `basis`, and
`basis_edge_ids` in `payload_json`. Projection views read those feature nodes;
they must not recompute the same decision from word counts, section names, or
path-specific case lists.

Projection may also carry corpus hints and the LocalLLM prose IR artifact path.
Corpus hints select the field-specific norms used to interpret rhetorical moves,
expected evidence, diagrams, formulas, and evaluation criteria. They should be
inferred from the LocalLLM IR extraction pass over source text, user prompt, and
optional term inputs, because prompt context may identify the intended academic
field before the draft does.

Projection implementations may use:

- graph contraction over support, prerequisite, refinement, and conclusion
  edges;
- quotient graph construction over anchor nodes grouped by shared purpose,
  topic, rhetorical move, or reader-state transition;
- topological sorting only on the selected ordering subgraph;
- strongly connected component contraction when dependency-like edges produce
  cycles;
- source order as a tie-breaker, never as sole evidence for macro roles.

Projection implementations must not:

- classify macro prose roles sequentially and then treat those labels as
  canonical truth;
- require every possible projection object to be written out;
- let a generated projection view mutate source text without an explicit edit
  operation;
- hide the member anchor ids and inference basis for a projection view.

## Projection And Ordering

A graph-to-text projection selects an ordering subgraph and emits a reader
sequence. A projection must not topologically sort the full layered graph.

Projection order must use this priority:

1. `presentation` edges with `order_kind=hard_before`.
1. Form containment from section to paragraph to sentence.
1. Requested profile constraints such as `writing`, `logic`, `experiment`,
   `report`, `academic`, `paper`, or `all`.
1. Phase preferences when the profile asks for genre move order.
1. Discourse edges with `order_kind=adjacency_preferred` as soft queue
   priorities, not hard topological constraints.
1. Confidence score for soft ordering evidence.
1. Source order as the final stable tie-breaker.

If the hard selected ordering constraints have a cycle, the projection must
record a diagnostic instead of silently dropping edges. A reorder edit
operation may propose a priority topological sort, but the rewrite packet must
preserve source ids and explain which hard constraints were relaxed. Soft
`adjacency_preferred` conflicts influence priority and cannot by themselves
force a topology cycle.

Current MVP projection exports emit nodes, edges, diagnostics, edit operations,
and `selected_ordering`. The `selected_ordering` object is the whole-document
sentence-anchor order produced by priority topological sort over the selected
ordering subgraph. Writing adapters use `selected_ordering.ordered_anchors` as
the DSL-to-prose input sequence, giving the LLM a deterministic reader-order
contract for the entire source text. Projection-view implementations should
extend that export with derived
macro views while still emitting source anchors, selected ordering
edges, diagnostics, and edit operations. Full internal analysis nodes are
available through debug-oriented projection exports for receiving skills and
reviewers that need complete graph evidence.

## Graph Visualization Contract

Graph visualization is a projection surface over this DSL object model. A
visual artifact may be Markdown, Mermaid, DOT, SVG, or self-contained HTML, but
its authority comes from the graph objects it projects: document records, node
records, edge records, diagnostics, projection views, presentation features,
adapter metadata, and `payload_json` provenance.

Reusable graph renderers should consume a DSL projection payload or an adapter
payload that can be losslessly mapped into DSL nodes and edges. Domain tools may
still own source-specific extraction. For example, dependency-manifest graph
TSV, semantic-provider comparison JSON, runtime-dashboard decision flows, and
JIT-canonical IR / Lean evidence records are adapter inputs. Their visual
reports are review projections over source facts, while the source checker,
proof checker, semantic-index command, or dashboard producer keeps domain
validation authority.

Every graph visualization adapter records this boundary:

- `adapter_name` and `adapter_version` identify the source extractor or legacy
  renderer.
- source nodes preserve path, symbol, document, provider, run, or other native
  locators in `payload_json`.
- edge kinds reuse registered relation vocabulary when available and otherwise
  use an adapter extension namespace.
- projection output preserves member node ids, source locators, edge basis,
  diagnostic ids, and renderer decisions.
- HTML or SVG viewers are inspection artifacts generated from projection data;
  they are reproducible outputs with projected provenance and renderer
  decisions.

The canonical implementation direction is a shared `prose_reasoning_graph.py`
projection / visualization entrypoint fed by adapters. Existing domain-specific
renderers remain valid while they document their adapter mapping and route
future reusable graph UI behavior through this contract.

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

## Verification Route Contract

Uncertain logic and uncertain paragraph connections must not be silently
rewritten as if they were settled. Diagnostics that identify unsupported claims,
missing warrants, weak bridges, or incomplete experiment plans should include a
`suggested_action_json.verification_route` object with:

- `verification_route`: stable route id such as
  `claim_support_verification`, `connection_verification`, or
  `experiment_plan_verification`;
- `verification_question`: the exact question that must be answered before
  rewrite;
- `verification_targets`: receiving skills or reviewers that can answer the
  question;
- `conditional_verification_targets`: optional routes such as
  `$formal-proof-workflow` when the claim is mathematical, proof-like, or
  implementation-derived;
- `evidence_required`: artifacts or source-packet fields needed to settle the
  question;
- `recursive_verification`: skill-local expansion policy with `max_depth`,
  `closure_condition`, `unresolved_leaf_policy`, and ordered `steps`.

Each recursive step must include:

- `id`: stable step id inside the route;
- `route`: skill or reviewer that owns the child question;
- `question`: child question to answer;
- `if_unresolved`: how to create the next child verification item or unresolved
  leaf record.

Recursive expansion is bounded by `max_depth` and by the closure condition, not
by agent patience. If a child remains unresolved at the bound, the workflow must
record an unresolved leaf with owner, route, missing evidence, and next
verification command. It must not convert that leaf into settled prose.

The route semantics are:

- `logic-gap-review` verifies inference validity, missing premises, and
  warrants;
- `$literature-survey` and `citation-evidence-review` verify external factual
  or scholarly support;
- `$formal-proof-workflow` verifies mathematical, proof-like, or
  implementation-derived claims through proof obligations or checker evidence;
- `$experiment-lifecycle` verifies testable empirical claims and experiment
  plan completeness;
- `$structure-planning` verifies reader-state transitions, section placement,
  and discourse connection decisions.

## Diagnostics Contract

Diagnostic rule ids are stable public contract. The current MVP implementation
emits:

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
- `presentation_format_candidate`: a projection view has a presentation feature
  subgraph showing that a non-prose form such as a list, table, figure, or
  equation may communicate the same anchored content better than prose.
- `selected_ordering_cycle`: hard selected-ordering constraints contain a cycle
  that must be relaxed, split, or corrected before reader-order projection is
  treated as settled.

The canonical-graph and projection-view contract reserves these rule ids for
implementations that enforce the new projection model:

- `missing_implicit_premise`: a text unit requires an unstated premise.
- `missing_warrant`: a support relation lacks the warrant that licenses the
  inference.

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

Visualization adapters follow the same rule. A dependency graph renderer maps
manifest edges into `artifact` nodes and dependency edges; a proof or JIT
viewer maps JIT-canonical records, Lean evidence definitions, and proof-status
payloads into adapter nodes and projection edges; a semantic-provider HTML
report maps provider deltas into artifact or projection nodes with comparison
payloads. Each adapter may keep its source-specific CLI while the shared
projection contract remains this DSL.

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
