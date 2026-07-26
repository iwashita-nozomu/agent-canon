<!--
@dependency-start
contract design
responsibility Defines the one-unit implementation contract for the parent-owned AgentCanon knowledge graph.
upstream design graph_architecture_audit.md accepted graph, completeness, provenance, and atomic-publication basis
upstream design ../../../documents/structured-analysis/graph-dsl.md reusable SQLite graph storage and projection contract
upstream design ../../../documents/dependency-manifest-design.md dependency-header grammar and producer boundary
upstream design ../../../documents/structured-analysis/dependency-header-analysis.md dependency adapter and claim-evidence trace
upstream design ../../../documents/semantic_index.md semantic-index store and context-cell contract
upstream design ../../../documents/search-coordination.md search/context ownership and advisory boundary
upstream design ../../../documents/responsibility-scope-management.md responsibility and import producer boundary
upstream design ../../../documents/SHARED_RUNTIME_SURFACES.md parent/submodule ownership and root-view policy
upstream implementation ../../../rust/agent-canon/src/dependency_manifest.rs current manifest parser and source snapshot producer
upstream implementation ../../../rust/agent-canon/src/structured_analysis.rs current Graph DSL materializer and contract checker
upstream implementation ../../../rust/agent-canon/src/semantic_index.rs current semantic-index store and context producer
upstream implementation ../../../tools/agent_tools/import_responsibility.py current Python import-edge producer
upstream implementation ../../../tools/agent_tools/responsibility_scope.py current responsibility-scope producer
downstream implementation ../../../rust/agent-canon/src/main.rs dispatches the public graph CLI
downstream implementation ../../../tools/agent_tools/graph_client.py provides the canonical Python graph consumer adapter
downstream implementation ../../../tools/agent_tools/check_design_doc_claims.py consumes graph path/evidence queries
downstream implementation ../../../tools/agent_tools/check_dependency_headers.py consumes canonical manifest context evidence
downstream implementation ../../../tools/agent_tools/search.py consumes canonical dependency query facts for header-deps search
downstream implementation ../../../tools/agent_tools/tool_drift.py consumes canonical dependency query facts for drift policy
downstream implementation ../../../tools/agent_tools/tool_catalog.py token-parses the fixed manual Rust public dispatch
downstream design graph_design_review.md detailed-design review gate for this artifact
downstream design graph_document_flow_review.md document-flow review gate for this artifact
@dependency-end
-->

# Detailed Design: One Parent-Owned AgentCanon Knowledge-Graph Unit

Run ID: `20260712-090608-context-packettool-skill-routing`
Design path: `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md`
Decision state: `design-revision-ready-for-same-SHA-review`
Review status: `pending`; findings 1–5 are repaired in this revision and both
same-SHA review gates must be rerun.
Write scope: this file only. This document is a design handoff, not an implementation claim.

Authority marker: `review_target_body_sha256=61804014791038554a38d79d0f983d67f354b881cbd7993b738ec651fe3ed5f8`

The authority marker line itself is excluded when computing
`review_target_body_sha256`; the value is the SHA-256 of the exact UTF-8 file
bytes after removing only that one line. The final handoff also reports the
full-file SHA-256 used by the same-SHA review. This rule makes the governing
revision independently identifiable without a self-referential hash field.
Therefore the marker is expected to differ from the full-file SHA; approval
requires both the marker-excluded body comparison and the separately reported
full-file SHA comparison.

## Abstract Design Frame

This one replaceable unit owns parent-repository graph construction and exact
evidence projection. The existing `Graph DSL` means the SQLite-backed
structured-analysis graph schema, materializer, and `graph-contract` validator;
this unit reuses that canonical storage contract and adds no second graph
schema. AgentCanon owns the generic mechanism and CLI; the parent owns
`.agent-canon/knowledge-graph/graph.sqlite`; authoritative producers own
language, parser, compiler, config, build, owner, import, and search facts.

`RepoPath` is a normalized parent-relative slash path; `SourceSpan =
{path:RepoPath,start_line:u64,start_column:u64,end_line:u64,end_column:u64}`;
`RelationKind = {dependency,owner,scope,import,include,symbol,call,containment,document,catalog,pin,view,generated,submodule,public}`.
`Hex64` is a lowercase 64-hex-character SHA-256 string. Existing producer
records are declared before their use: `tool_catalog.py::Finding =
{check:String,path:String,detail:String}`, `CatalogRow =
{tool_id:String,path:String,summary:String,family:String,role:String,status:String,audience:String,placement:String,command:String|null,writes:bool,ci:bool,pr_check:bool,docs:Vec<String>,tests:Vec<String>}`,
and `CatalogReport = {findings:Vec<Finding>,entries:Vec<CatalogRow>}`;
`check_design_doc_claims.py::Finding =
{kind:String,path:String,line:u64,detail:String}` is a separate namespaced
record. `DiagnosticSet = {Unresolved,Ambiguous,Uncovered,Excluded}`,
`DiagnosticSeverity = {Info,Warn,Blocker}`, and
`GraphDiagnostic = {id:String,set:DiagnosticSet,code:String,severity:DiagnosticSeverity,relation:RelationKind|null,path:RepoPath|null,target:RepoPath|null,source_span:SourceSpan|null,reason:String,producer:String|null,evidence_ref:String|null,suggested_action_json:String|null}`.
`EpochMillis = u64`; `RuntimeMeasurement = {responsibility_unit_id:String,generation_parent:String|null,reuse_mode:String|null,packet_hash:Hex64|null,context_bytes_by_source:BTreeMap<String,u64>,finding_iteration:u64|null,review_iteration:u64|null,writer_ids:Vec<String>,reviewer_ids:Vec<String>,launch_epoch:EpochMillis|null,finish_epoch:EpochMillis|null,input_tokens:u64|null,cached_input_tokens:u64|null,output_tokens:u64|null,reasoning_tokens:u64|null,retries:u64|null,waits:u64|null,progress_bytes:u64|null,repeated_artifact_hashes:Vec<Hex64>}`. Runtime measurements are producer-owned observations, not inferred graph facts; numeric `null` means the producer did not record that measurement, while `0` means it explicitly recorded zero.
`GraphError = {Usage(String), Producer{producer:String,reason:String}, Validation{stage:String,reason:String}, CandidateWrite{reason:String}, CandidateSync{reason:String}, Rename{reason:String}, DirectorySync{reason:String}, Unavailable{reason:String}}` and
`DurableGraphState = {Fresh,Missing,Stale,Incomplete,Invalid,SchemaMismatch,Unavailable}`
and `SemanticIndexState = {Available,Missing,Stale}`.

The public-surface producer interface is fixed here before any reuse-table
reference. `RepoPath` is a normalized parent-relative slash path and
`SourceSpan = {path:RepoPath,start_line:u64,start_column:u64,end_line:u64,end_column:u64}`.
`CachePath` is either a canonical `cache:<repo-key>/<name>` semantic-index
identifier or a normalized absolute UTF-8 path for an explicitly selected
semantic-index cache; it is never a graph DB path or a `RepoPath`.
`PublicSurfaceRow = {surface_id:str,kind:str,path:RepoPath,selector:str,source_span:SourceSpan,secondary_spans:list[SourceSpan],authority:str}`;
`PublicSurfaceReport = {producer_version:str,rows:list[PublicSurfaceRow],diagnostics:list[Finding]}`;
and `extract_public_surface(root: pathlib.Path) -> PublicSurfaceReport`.
`CatalogReport` remains the existing structure-catalog report. The producer
artifact is `CatalogBundle = {schema:"agent_canon.catalog_bundle.v1",catalog:CatalogReport,public:PublicSurfaceReport}`;
`catalog` and `public.rows` are distinct authority lanes, and no alternate
public report or compatibility decoder exists.

The canonical graph type declarations referenced throughout this brief are:
`RelationKind = {dependency,owner,scope,import,include,symbol,call,containment,document,catalog,pin,view,generated,submodule,public}`;
`RelationSelector = all|RelationKind`; `GraphDirection = {Outgoing,Incoming,Both}`;
`ProducerArtifact = {producer_id:String,version:String,command:String,root:RepoPath,content_sha256:Hex64,relation_families:Vec<RelationKind>,artifact_ref:String}`;
`artifact_ref` is the stable logical reference
`producer:<producer_id>/<relative-artifact-path>#sha256=<content_sha256>`;
`relative-artifact-path` is relative to the stable logical producer root,
never a candidate-temp path. In this unit `ProducerArtifact.root` is the
normalized parent root `.` (the producer input root), and the runtime artifact
path is exactly `runtime-dashboard.json`; therefore its stable reference is
`producer:runtime-dashboard/runtime-dashboard.json#sha256=<Hex64>`. The
candidate may delete its temporary output bytes after hashing; the durable
graph retains this logical reference, hash, producer command/version, and the
complete normalized output bytes under the existing Graph DSL metadata key
`producer_artifact_payloads`, whose canonical JSON map key is exactly
`<producer_id>:<content_sha256>` and whose value is the complete output bytes
encoded as standard padded RFC-4648 Base64, before candidate
cleanup. `context` resolves an artifact reference only through that map entry,
verifies the stored bytes against the hash, and returns the exact reference and
hash; it never reopens the deleted candidate file or guesses an archive path.
For this unit `<candidate-temp>` is the normalized parent-relative path
`.agent-canon/knowledge-graph/.candidate/<build-id>`. Runtime raw-log and
run-result ownership remains with the canonical archive producers; their
paths are provenance inputs, not `artifact_ref` values.
`DependencyFactDetail = {direction:String,kind:String,reason:String}` with
`direction=upstream|downstream` and
`kind=design|implementation|environment`; it is non-null only when
`GraphQueryFact.kind=dependency` and is copied from the authoritative
`ManifestParser` declaration without consumer reparsing.
`GraphNode = {id:String,path:RepoPath|null,selector:String,layer:String,kind:String,owner:String|null,source_path:RepoPath|null,source_span:SourceSpan|null,distance:u8}`;
`GraphQueryFact = {id:String,layer:String,kind:RelationKind,from:String,to:String|null,owner:String|null,source_path:RepoPath|null,source_span:SourceSpan|null,producer:String,evidence_ref:String,authority:String,inferred:bool,dependency_detail:DependencyFactDetail|null}`;
`DependencyWitness = {edge_id:String,relation:RelationKind,from:RepoPath,to:RepoPath,owner:String|null,source_path:RepoPath,source_span:SourceSpan|null,producer:String,evidence_ref:String,authority:String}`;
`GraphContextItem = {kind:String,value:String,source_store:String,producer:String|null,source_path:RepoPath|null,source_span:SourceSpan|null,evidence_ref:String|null,authority:String,rank:u64|null,score:f64|null,bucket:String|null,excerpt:String|null,cache_state:SemanticIndexState|null}`;
`GraphIntegrationRecord = {schema:String,root:RepoPath,db_path:RepoPath,schema_version:String,profile:String,source_snapshot_profile:String,snapshot_head:String,input_fingerprint:Hex64,graph_fingerprint:Hex64,producer_artifacts:Vec<ProducerArtifact>,verified:bool,verification_code:String}`;
`GraphStatusCode = {Fresh,Missing,Stale,Incomplete,Invalid,SchemaMismatch,Unavailable,BuildFailed,PublicationFailed}`;
`OutputFormat = {Text,Json}`; `PublicationState = {Published,Unchanged,NotPublished}`;
`DurabilityState = {Durable,Uncertain,NotDurable}`;
`GraphContextEvidence = {path:PathBuf,source_span:Option<SourceSpan>,owner:Option<String>,content_sha256:Option<Hex64>,cache_state:SemanticIndexState,rank:u64,score:f64,kind:String,bucket:String,excerpt:String}`;
`GraphStatusResponse = {schema:String,command:String,status:GraphStatusCode,profile:String,root:RepoPath,db_path:RepoPath,input_fingerprint:Hex64|null,graph_fingerprint:Hex64|null,integration_record:GraphIntegrationRecord|null,unresolved_count:u64,ambiguous_count:u64,uncovered_count:u64,excluded_count:u64,unresolved:Vec<GraphDiagnostic>,ambiguous:Vec<GraphDiagnostic>,uncovered:Vec<GraphDiagnostic>,excluded:Vec<GraphDiagnostic>,reason:String|null,stderr_summary:String|null,producer_id:String|null,failure_stage:String|null,exit_code:u8}`;
`GraphBuildResponse = {schema:String,command:String,status:GraphStatusCode,graph_status:DurableGraphState|null,profile:String,root:RepoPath,db_path:RepoPath,input_fingerprint:Hex64|null,graph_fingerprint:Hex64|null,unresolved_count:u64,ambiguous_count:u64,uncovered_count:u64,excluded_count:u64,unresolved:Vec<GraphDiagnostic>,ambiguous:Vec<GraphDiagnostic>,uncovered:Vec<GraphDiagnostic>,excluded:Vec<GraphDiagnostic>,reason:String|null,stderr_summary:String|null,publication:PublicationState,durability:DurabilityState,failure_stage:String|null,exit_code:u8,producer_artifacts:Vec<ProducerArtifact>}`;
`GraphQueryResult = {schema:String,status:GraphStatusCode,profile:String,root:RepoPath,db_path:RepoPath,path:RepoPath|null,all:bool,relation:RelationSelector,direction:GraphDirection,depth:u8,graph_fingerprint:Hex64|null,reason:String|null,stderr_summary:String|null,exit_code:u8,unresolved_count:u64,ambiguous_count:u64,uncovered_count:u64,excluded_count:u64,nodes:Vec<GraphNode>,facts:Vec<GraphQueryFact>,unresolved:Vec<GraphDiagnostic>,ambiguous:Vec<GraphDiagnostic>,uncovered:Vec<GraphDiagnostic>,excluded:Vec<GraphDiagnostic>}`;
`GraphContextResult = {schema:String,status:GraphStatusCode,profile:String,root:RepoPath,db_path:RepoPath,claim_path:RepoPath,token:String|null,resolved_path:RepoPath|null,source_span:SourceSpan|null,owner:String|null,dependency_witnesses:Vec<DependencyWitness>,items:Vec<GraphContextItem>,runtime_measurements:Vec<RuntimeMeasurement>,context_diagnostics:Vec<GraphDiagnostic>,producer:String|null,semantic_index:SemanticIndexState,semantic_index_path:CachePath|null,semantic_index_content_sha256:Hex64|null,graph_fingerprint:Hex64|null,reason:String|null,stderr_summary:String|null,exit_code:u8,unresolved_count:u64,ambiguous_count:u64,uncovered_count:u64,excluded_count:u64,unresolved:Vec<GraphDiagnostic>,ambiguous:Vec<GraphDiagnostic>,uncovered:Vec<GraphDiagnostic>,excluded:Vec<GraphDiagnostic>}`; `DependencyWitness` and `GraphContextItem` are the evidence records defined in the mathematical contract. `GraphResponse = {schema:String,command:String,status:String,payload:Mapping[str,object],exit_code:int}` is the Python adapter record, and `GraphDependencyFact = {id:str,direction:str,kind:str,source:str,target:str,reason:str,producer:str,source_path:str|null,source_span:Mapping[str,object]|null,evidence_ref:str,authority:str}` is its one canonical typed dependency projection for all Python consumers.

The capitalized declarations above are the implementation-language records and
enums. The quoted lower-case objects in the CLI section are their canonical
JSON serialization: field presence, nullability, enum values, and array
ordering are identical, with only casing and container notation translated.
There is no separate wire schema or compatibility projection.
Wire enum mapping is explicit: `Fresh→fresh`, `Missing→missing`, `Stale→stale`,
`Incomplete→incomplete`, `Invalid→invalid`, `SchemaMismatch→schema-mismatch`,
`Unavailable→unavailable`, `BuildFailed→build-failed`,
`PublicationFailed→publication-failed`; `Info→info`, `Warn→warn`, and
`Blocker→blocker`; `Available→available`. All other enum strings retain their
lowercase spelling. This is the only implementation-type to JSON mapping.

The layer order is `source snapshot -> scope -> producer facts -> Graph DSL
materialization -> query/context projections -> review diagnostics`. Let `S`
be the stable source snapshot and producer-input state captured for one build.
The core terms used in the opening structure are: `P(S)` candidate sources,
`X(S)` explicit exclusions, `U(S)=P(S)\X(S)` eligible sources, `D` manifest
declarations, `O` raw observed relations with extractor provenance, `R` the
accepted authoritative relation set after reconciliation, `G` the materialized
graph, and `Vp` a profile projection derived from `G`. Let `p` be the selected
producer profile (`default` in version one). `Unresolved(S,p)` and
`Ambiguous(S,p)` are explicit diagnostic sets, never silently dropped rows.
`A = Unresolved(S,p) ∪ Ambiguous(S,p)` is their diagnostic union, not a
producer record. `X_R(S,p)` is a relation-level exclusion with producer, rule,
and reason, distinct from source-path `X(S)`. `P_scan = {p ∈ U(S) | p is an existing regular non-symlink
file and p has suffix .py, .c, .cc, .cpp, .h, .hpp, .sh, .bash, or .zsh}`;
unsupported suffixes remain in `U(S)` for other producers and are classified
only as scanner relation `X_R` before this set is formed.
“Luna worker” means the repository's configured `worker` role running the
`gpt-5.6-luna` model at its role-defined high-assurance setting; it is one
accountable writer identity, not a second implementation route.

The public surface is only `agent-canon graph build|status|query|context`.
Here `R2` means the rejected private normalized-record/binder transport route
from the current branch; Graph DSL/structured-analysis/semantic-index stores
are reused, while MCP, private R2/byte-schema/binder routes, duplicate parsers, and graph-owned language or
compiler semantics are excluded. Evaluation is by ownership, producer
authority, completeness, freshness, atomic publication, reverse-edge closure,
context evidence, reuse, and obsolete-route cleanup. The detailed frame below
fixes the same decisions before the file plan.

The accountable implementation writer is one Luna `worker` for this entire
replaceable unit; the parent session is the orchestrator/integrator and owns
scope formation, review gates, validation evidence, and closeout. No
file-sized or finding-sized writer identity is introduced. The same writer
must carry dirty semantic intent through source, consumers, docs/skills,
generated views, dependency edges, and stale-fixture cleanup in the dependency
order below.

Gate order is also explicit:
this current brief is a predecessor design whose implementation may be handed
off only after fresh same-SHA detailed-design and document-flow approval; only
successor designs, after source integration, require the archived predecessor
integration-record verifier. A pending successor record never authorizes this
brief or any successor from a mutable design SHA.

The named handoff contracts are defined before the reader map uses them:
`SP-1` is request/branch evidence, `SP-2` is mathematical/current basis,
`SP-3` is source/symbol evidence, `SP-4` is dirty/deletion scope, `SP-5` is
binding scope, and `SP-6` is review/validation; together they are the
mandatory `Source Packet` read-before-edit index.
`Design Side-Effect Map` is the `SEM-*` owner/review/validation/surface join;
`Design-To-Implementation Trace` is the canonical `SEM-*` edit-to-clause/
reuse/validation join; `TR-1`–`TR-7` are only its preflight summary rows.
`Current dirty-path disposition` is the exact modified/untracked-path
preservation table; and `Explicit deletion list` is the source-first obsolete
R2/binder/byte-schema/parser/fixture removal table. Each is expanded later
without changing its contract. `Reverse-edge closure` means that every
accepted fact `f:from→to` has the deterministic swapped projection
`reverse:f` with the same evidence reference and `inferred=true`, and that
outgoing/incoming/both queries return both members. `Successor predecessor
gate` means that only the verified archived
`agent_canon.predecessor_integration.v1` record bound to the integrated source
OID authorizes a successor; this brief's marker, pending SHA, or review text
never does.

## Reader Map

Read the Abstract Design Frame first, followed by the Structure Contract,
request/branch clause IDs, detailed frame, reuse survey, mathematical contract,
public CLI, lifecycle contract, and one-unit change plan. The Source Packet is
the mandatory read-before-edit list; the Side-Effect Map and Trace are the
implementation and review joins.

## Structure Contract

- `structure_kind`: implementation-ready design brief.
- `audience`: the single writer, detailed-design reviewer, document-flow reviewer, and parent integration reviewer.
- `document_unit.owner`: AgentCanon detailed-design owner for the parent knowledge-graph responsibility.
- `document_unit.reader`: the implementation writer and reviewers who need one context-independent contract.
- `document_unit.source_map`: `graph_architecture_audit.md`, current Rust/Python producers, Graph DSL, semantic-index, dependency-manifest, branch/dirty evidence.
- `document_unit.validation_route`: same-SHA detailed-design review, document-flow review, Markdown check, dependency-header check, then implementation validation selected by this design.
- `document_unit.update_cadence`: update when the graph public contract, producer authority, storage owner, or implementation boundary changes.
- `document_unit.canonical_parent`: `graph_architecture_audit.md` for mathematical and ownership basis; this brief is the implementation contract.
- `document_unit.downstream_consumers`: `rust/agent-canon/src/main.rs`, the future `graph` module, graph consumers, CLI/docs/skills, and the parent repository's generated graph path.
- `document_split_decision`: `keep:same owner, reader, source map, validation route, and update cadence; files are implementation surfaces, not document split boundaries`.
- `structure_first_artifact`: the Abstract Design Frame and its ownership/layer diagram.
- `structure_visual_plan`: `mermaid`; the diagram shows producer-to-graph-to-consumer authority flow.
- `invalid_interpretations`: the diagram and graph are not language/compiler/config truth, citation approval, PR approval, MCP, or a second source parser.

```mermaid
flowchart LR
  A[Authoritative producers] --> B[P(S), X(S), U(S)]
  A --> C[D and R with owner/source evidence]
  B --> D[One graph build unit]
  C --> D
  D --> E[G in parent .agent-canon/knowledge-graph/graph.sqlite]
  E --> F[Vp query projection]
  E --> H[Exact context evidence]
  F --> I[check_design_doc_claims consumer]
  H --> J[search and workflow consumers]
```

## Request and branch clause IDs

The implementation packet uses these IDs so the writer does not infer scope
from chat context.

| ID | Contract |
| --- | --- |
| `KG-1` | Expose one generic AgentCanon CLI: `graph build`, `graph status`, `graph query`, `graph context`. |
| `KG-2` | The parent repository owns `.agent-canon/knowledge-graph/graph.sqlite`; AgentCanon owns reusable mechanism, not parent state. |
| `KG-3` | Use no MCP, no private R2 route, no byte-schema/binder, and no duplicate Python transport/fact store. |
| `KG-4` | Use one dependency-manifest parser with no line scan limit; derive relations from authoritative producers. |
| `KG-5` | Reuse Graph DSL, structured-analysis, semantic-index stores, existing owner/source/dependency tools, and their provenance. |
| `KG-6` | Express completeness with `P(S)`, `X(S)`, `U(S)`, `D`, `R`, `G`, `Vp`, and explicit unresolved and ambiguous sets. |
| `KG-7` | Build is atomic and freshness-aware; context returns exact owner, source, and dependency evidence. |
| `KG-8` | Language/parser/compiler/config/build facts remain with authoritative tools; the graph adds owner, dependency, projection, cross-file, and public semantics only. |
| `KG-9` | One writer completes source, schema, CLI, consumers, docs, skills, dependency edges, and stale-test removal in one replaceable unit; source mechanism precedes public regression/property coverage. |
| `BR-1` | `origin/main..HEAD` contains `ecacb84b`, `24c878b4`, `0a7cc98a`, and `607c8e81`; their approximately 18k lines are one incoherent transport/fact-authority route to be consolidated. |
| `BR-2` | Dirty intent exists in `check_design_doc_claims.py`, its docs/tests, `bind_r2_scope.py`, dependency-manifest Rust/Python, and three tracked-style fixtures; preserve semantic intent before deleting obsolete matrices. |
| `BR-3` | There is no PR; the result is one coherent graph/source PR, not a historical R2-internals PR. |
| `RT-1` | Include the measured runtime/dashboard repair in this graph unit: typed event-derived path normalization/rejection, canonical workflow attribution ownership, and zero-versus-missing token evidence. |
| `RT-2` | Preserve and expose the exact runtime measurement fields: responsibility unit, generation parent/reuse, packet hash, context bytes by source, finding/review iterations, writer/reviewer IDs, launch/finish, input/cached/output/reasoning tokens, retries, waits, progress bytes, and repeated artifact hashes. |
| `RT-3` | Reuse `generate_agent_runtime_dashboard.py`, `compare_codex_token_footprints.py`, and `workflow_monitor.py` as the only runtime producers; add no duplicate logger/schema or graph-side raw-log parser. |

### Packet-ID legend

The packet namespaces are defined before any crosswalk uses them. For each
preserved `SEARCH-1..SEARCH-8`, `SEARCH-n-N*` is the prohibited-route check and
`SEARCH-n-C*` is the positive coverage check. `F6` is graph population and
provenance, `F7` freshness/materialization, `F8` coverage/reconciliation, `F9`
query/bounded context, and `F10` proof boundary. Their required routing fields
are `finding_class`, `evidence_cells`, `route_target`, `instance_partition`,
`required_packet`, and `closeout_gate`.

The handoff routing rows are declared here before the crosswalk and
implementation plan; the expanded Side-Effect Map/Trace joins later preserve
the same values.

| Packet IDs | finding_class | evidence_cells | route_target | instance_partition | required_packet | closeout_gate |
| --- | --- | --- | --- | --- | --- | --- |
| `SEARCH-1-N*`, `SEARCH-1-C*` | `structure_boundary` | structure/root/view/submodule status | structure owner | `path_scope` | canonical boundary + source-universe decision | structure contract or typed issue |
| `SEARCH-2-N*`, `SEARCH-2-C*` | `owner_identification` | responsibility/owner spans | responsibility owner | `owner_scope` | owner map + replaceable unit | owner/scope evidence |
| `SEARCH-3-N*`, `SEARCH-3-C*` | `query_plan` | relation family/universe/reuse/signal | query owner | `relation_family` | query row + stop/next decision | reproducible query or typed gap |
| `SEARCH-4-N*`, `SEARCH-4-C*` | `evidence_promotion` | authority/freshness/impact/context | context owner | `evidence_cell` | fact + provenance + artifact | exact evidence or typed gap |
| `SEARCH-5-N*`, `SEARCH-5-C*` | `research_escalation` | typed stale/missing/coverage/conflict status | owning producer/planning gate | `finding_partition` | trigger + owner + packet | re-search or escalation |
| `SEARCH-6-N*`, `SEARCH-6-C*` | `canonical_routing` | canonical active/deferred/private route | canonical owner | `route_surface` | source path + route decision | canonical route; private absent |
| `SEARCH-7-N*`, `SEARCH-7-C*` | `recurrence_prevention` | evidence cell/owner/partition/gate | finding owner | `finding_partition` | recurrence packet | closure or typed deferral |
| `SEARCH-8-N*`, `SEARCH-8-C*` | `bounded_context` | facts/provenance/diagnostic counts | context owner | `query_scope` | bounded context + risks | no stale promotion |
| `F6` | `graph_population` | source manifest + `U/D/O/G/X/A` + provenance | Graph DSL/dependency owners | `parent_root|relation_family` | manifest + extractor + identity map + assertion | two-build/lossless reconciliation |
| `F7` | `graph_freshness` | HEAD/dirty/hash/pin/schema/status | freshness owner | `parent_root|source_change_kind` | before/after + add/modify/delete + atomic result | status matrix/no silent rebuild |
| `F8` | `graph_coverage` | `V(G)`/`O\\D`/`D\\O`/uncovered/A/X | coverage reviewers | `relation_family` | universe + reconciliation + reasons | finite-set checks or visible escalation |
| `F9` | `graph_query` | query matrix/provenance/status/context | query/CLI owners | `relation_family|query_scope` | plan + status + facts + artifact | reproducible/no stale claim |
| `F10` | `graph_proof_boundary` | executable oracle/adversarial/formal selection | validation/formal owner | `normalization|projection|closure` | assumption + oracle + proof target/non-target | no parser-completeness claim |

### Current-contract crosswalk

The two requirements artifacts are read-before-edit authority for the broader
coverage/search contract. These joins prevent the implementation writer from
using only the abbreviated local IDs above.

The current-contract namespaces mean: `KG-A..KG-J` = (A) CLI-first/no MCP,
(B) reusable AgentCanon behavior with parent-owned state, (C) parent inputs and
pin/view provenance, (D) deterministic lifecycle/fingerprints/status,
(E) relative coverage sets, (F) declaration-plus-observation reconciliation,
(G) finite-set proof boundary, (H) unified CLI/context, (I) no fallback or
silent loss, and (J) completion reproducibility/freshness/query evidence.
`KG-C1..KG-C10` are the acceptance checks for fixed path/build, fingerprints
and no-silent-rebuild, `U/D/O/G/X/A` executable checks, reconciliation counts,
two-build plus add/modify/delete freshness, relation-family queries/context,
adversarial fixtures, proof boundary, canonical CLI, and no-MCP targeted
closeout. `SEARCH-1..SEARCH-8` preserve structure-first intake, owner
identification, query planning, evidence promotion, re-search/escalation,
canonical routing, recurrence packets, and coverage-complete bounded context.
Here `A = Unresolved(S,p) ∪ Ambiguous(S,p)`; it is a diagnostic-set union, not
an additional producer record type. The local `KG-C1..KG-C10` labels are
implementation shorthand only; the exact
source acceptance IDs are `KG-AC1..KG-AC10`, and the continuity table below
maps them without renaming the source contract. `KG-N1..KG-N6` are the exact
must-not-do constraints and are mapped to their guards and oracles there.

The `SEM-*` labels used in the crosswalks are defined here before any reference:
`SEM-01` one parser/full-file scan; `SEM-02` parent-owned DB; `SEM-03` Graph
DSL storage; `SEM-04` producer-owned `D`/`R`; `SEM-05` explicit unresolved and
ambiguous sets; `SEM-06` atomic/freshness lifecycle; `SEM-07` graph-backed claim
checker; `SEM-08` R2 transport/binder removal; `SEM-09` one graph CLI;
`SEM-10` search consumers; and `SEM-11` runtime evidence/dashboard repair.
The authoritative descriptions and full side-effect
joins remain in the Side-Effect Map below.

| Current contract IDs | Design map IDs / implementation consequence |
| --- | --- |
| `KG-A`, `KG-B` | `SEM-02`, `SEM-03`, `SEM-09`: CLI-first reusable AgentCanon mechanism and one parent-owned DB. |
| `KG-C` | `SEM-01`, `SEM-04`, `SEM-10`: git-visible parent inputs, producer facts, catalogs, and pin/view provenance; AgentCanon submodule internals excluded. |
| `KG-D` | `SEM-06`: deterministic source manifest, HEAD/dirty/content/pin/schema/tool fingerprints, atomic update, and no silent rebuild. |
| `KG-E`, `KG-F` | `SEM-01`, `SEM-04`, `SEM-05`: `U,D,O,G,X,A`, relation-family reconciliation, reverse edges, unsupported/generated/view/submodule semantics, and owner linkage. |
| `KG-G` | `SEM-05`, `SEM-08`: executable finite-set/property boundary only; no parser/source-completeness formal proof. |
| `KG-H` | `SEM-07`, `SEM-09`: unified CLI and bounded context are canonical; MCP remains excluded. |
| `KG-I` | `SEM-07`, `SEM-08`, `SEM-10`: no keyword-only route, compatibility fallback, silent loss, or broad-CI shortcut. |
| `KG-J` | `SEM-05`, `SEM-06`, `SEM-09`: two-build equality, add/modify/delete freshness, relation-family query, explicit counts, and targeted checks. |
| `KG-C1`, `KG-C2` | `SEM-02`, `SEM-06`: fixed path, source manifest, HEAD/dirty/content/pin/schema/tool fingerprints, and status contract. |
| `KG-C3`, `KG-C4` | `SEM-01`, `SEM-04`, `SEM-05`: executable `U,D,O,G,X,A` equalities, lossless provenance, reconciliation, and counts. |
| `KG-C5`, `KG-C6` | `SEM-06`, `SEM-07`, `SEM-09`: reproducible builds, add/modify/delete freshness, every relation-family query, bounded context, and claim invalidation. |
| `KG-C7`, `KG-C8` | `SEM-01`, `SEM-05`, `SEM-08`: adversarial/property coverage and proof boundary. |
| `KG-C9`, `KG-C10` | `SEM-09`, `SEM-08`: canonical CLI route, no MCP, and targeted static closeout. |
| `SEARCH-1..SEARCH-2` | `SEM-01` through `SEM-04`: structure-first source intake and owner/responsibility boundary. |
| `SEARCH-3..SEARCH-5` | `SEM-04`, `SEM-05`, `SEM-07`, `SEM-10`: relation-family query plan, evidence promotion, freshness/coverage gaps, re-search, and escalation. |
| `SEARCH-6..SEARCH-8` | `SEM-07`, `SEM-08`, `SEM-09`: canonical skill/tool route, finding packets, recurrence evidence, and coverage-complete bounded context. |

Validation oracle legend (the full executable contracts appear in the
Validation mapping section near the end): `1` structure, `2` complete-file
parser, `3` source scope, `3a` empty scanner scope, `4` producer authority,
`5` Graph DSL contract, `6` reverse closure, `7` atomicity, `8` freshness,
`9` completeness, `10` context evidence, `11` graph-backed consumer, `12`
R2/binder residual scan, `13` byte-schema/transport residual scan, `14`
duplicate-parser residual scan, `15` structured/search/catalog residual scan,
`16` MCP residual scan, `17` cleanup ordering, `18` reproducibility, `19`
add/modify/delete freshness, `20` relation-family query matrix, `21`
adversarial/property coverage, `22` runtime path normalization/rejection,
`23` runtime measurement field completeness, `24` workflow attribution,
`25` token producer coverage, `26` runtime projection/provenance, `27` exact
changed-file dependency checker, `28` direct coordinated-search consumer,
`29` symbol-complete drift consumer, `30` manual Rust dispatch/extractor, and
`31` public-to-producer profile mapping. `3a` is the only inserted sub-oracle; it is
defined before any ledger row can reference it.

| Exact search clause | Side-Effect Map owner | Validation oracle(s) |
| --- | --- | --- |
| `SEARCH-1` | `SEM-01`, `SEM-02`, `SEM-04` | 1, 3, 4: structure-first source intake records the parent scope, source universe, and producer witnesses. |
| `SEARCH-2` | `SEM-04`, `SEM-05` | 3, 4, 9, 10: owner identification is a graph projection with explicit unresolved/ambiguous evidence. |
| `SEARCH-3` | `SEM-04`, `SEM-07` | 6, 9, 20: query planning covers reverse closure, completeness diagnostics, and every relation family. |
| `SEARCH-4` | `SEM-04`, `SEM-07`, `SEM-10` | 4, 10, 11: evidence promotion preserves producer, source span, owner, dependency witness, and consumer behavior. |
| `SEARCH-5` | `SEM-05`, `SEM-06`, `SEM-07` | 8, 9, 19, 21: re-search/escalation exposes stale, unresolved, ambiguous, and adversarial cases without fallback. |
| `SEARCH-6` | `SEM-07`, `SEM-09` | 11, 16, 20: canonical routing uses the public graph CLI and graph-backed consumer queries, with no MCP route. |
| `SEARCH-7` | `SEM-06`, `SEM-08` | 7, 8, 17, 21: recurrence packets retain atomic failure/freshness evidence while obsolete transport matrices are removed after source checks. |
| `SEARCH-8` | `SEM-05`, `SEM-07`, `SEM-10` | 9, 10, 20, 21: bounded context is coverage-complete only when all diagnostics and exact evidence are returned. |

### Direct current-clause oracle ledger

The grouped crosswalk above is a reader summary; this ledger is the
implementation and review authority. Each original current-contract ID has one
direct Side-Effect Map join and numbered oracle set. The IDs are not renamed.

| Exact current ID | Side-Effect Map join | Numbered validation oracle(s) |
| --- | --- | --- |
| `KG-A` | `SEM-09`, `SEM-08` | 16, 20, 30: one generic four-command CLI, exact manual dispatch extraction, and no MCP graph route. |
| `KG-B` | `SEM-02`, `SEM-03`, `SEM-09` | 1, 5, 17: reusable AgentCanon mechanism, Graph DSL validation, and no duplicate public route. |
| `KG-C` | `SEM-01`, `SEM-02`, `SEM-04` | 3, 4, 19: parent inputs, pin/view provenance, and source/producer identity. |
| `KG-D` | `SEM-06` | 7, 8, 18, 19, 31: atomic publication, profile-bound fingerprint freshness, deterministic rebuild, and source changes. |
| `KG-E` | `SEM-01`, `SEM-05` | 3, 9, 20: `P(S)`, `X(S)`, `U(S)`, `D`, `R`, `G`, `Vp` and relation-family coverage. |
| `KG-F` | `SEM-04`, `SEM-05` | 4, 9, 20: declaration/observation reconciliation, `O\\D`, `D\\O`, unresolved, ambiguous, and excluded evidence. |
| `KG-G` | `SEM-05`, `SEM-08` | 9, 17, 21: finite executable proof boundary, retained diagnostics, and adversarial/property cases. |
| `KG-H` | `SEM-07`, `SEM-09` | 10, 11, 20: exact context evidence, graph-backed checker, and query matrix. |
| `KG-I` | `SEM-07`, `SEM-08`, `SEM-10` | 9, 11, 14, 15, 16, 27–29: no fallback, silent loss, duplicate parser, second consumer authority, or MCP route. |
| `KG-J` | `SEM-05`, `SEM-06`, `SEM-07` | 8, 9, 18, 19, 20: freshness, completeness, reproducibility, add/modify/delete, and query evidence. |
| `RT-1/RT-2/RT-3` | `SEM-11` | 22, 23, 24, 25, 26: typed runtime path rejection, complete measured fields, hook-owner attribution, canonical token evidence, and graph context provenance. |

### Deferred-clause continuity

The deferred IDs from the requirements contract remain explicit and are not
silently promoted to implementation authority. This graph design resolves the
named contract gaps where possible and preserves the remaining deferrals:

| Exact deferred ID | Disposition in this graph unit | Follow-up / escalation |
| --- | --- | --- |
| `KG-D1` | Resolved by the fixed Graph DSL schema/tool fingerprints, replacement-only schema policy, and `GraphIntegrationRecord`. | Reopen only if Graph DSL changes its canonical schema. |
| `KG-D2` | Resolved by `P(S)`, `X(S)`, `U(S)`, `P_scan`, producer ownership, relation matrix, reverse closure, and identity collision policy. | Reopen through dependency/responsibility/import/structure review for a new producer family. |
| `KG-D3` | Explicitly deferred: finite-set executable checks are required; no parser/source semantic-completeness proof is claimed. | Send only a proven nontrivial normalization/projection/closure rule to formal-proof design. |
| `KG-D4` | Explicitly rejected for this unit: the four public graph operations define no MCP capability gap. | Reopen only after a reproducible CLI failure demonstrates a capability gap; no compatibility path. |
| `KG-D5` | Resolved by this standalone graph design packet and its same-SHA review gate; the historical routing brief remains untouched. | A later scope contradiction returns to detailed-design review. |
| `SEARCH-1..SEARCH-8-D1` | Resolved for this unit by the owner-bounded API, naming, source mechanism, and no-wrapper/no-fallback contracts. | A successor design must consume the archived predecessor integration record. |
| `SEARCH-7-D2` | Resolved in this unit as `SEM-11` runtime evidence repair: dashboard measurements and typed attribution diagnostics are producer evidence, while they remain separate from graph completeness. | Keep raw runtime-result ownership with `result-artifact-writeout`/`agent-log-analysis`; graph consumes the canonical dashboard API and does not create a second logger or schema. |
| `SEARCH-8-D3` | Explicitly deferred: no numeric token-budget/savings claim is made. | Add only through later planning approval and a coverage oracle. |

### Exact acceptance and must-not-do continuity

| Exact source ID | Local design join | Side-Effect Map | Validation oracle(s) / disposition |
| --- | --- | --- | --- |
| `KG-AC1` | `KG-C1` | `SEM-02`, `SEM-06` | 3, 7, 18: fixed path, source universe, deterministic atomic build. |
| `KG-AC2` | `KG-C2` | `SEM-02`, `SEM-06` | 8, 19: HEAD/dirty/content/pin/schema/tool fingerprints and freshness. |
| `KG-AC3` | `KG-C2`, `KG-C6` | `SEM-06`, `SEM-07` | 8, 11, 31: profile-verified CLI non-fresh refusal, no silent rebuild, and typed build/status failure. |
| `KG-AC4` | `KG-C3` | `SEM-01`, `SEM-04`, `SEM-05` | 3, 4, 9, 18: `U,D,O,G,X,A`, lossless provenance, identity. |
| `KG-AC5` | `KG-C4` | `SEM-05` | 9, 20: `O\D`, `D\O`, uncovered/ambiguous/excluded counts. |
| `KG-AC6` | `KG-C3` | `SEM-01`, `SEM-02`, `SEM-05` | 3, 19, 21: canonical/view/generated/submodule identity and pin provenance. |
| `KG-AC7` | `KG-C7` | `SEM-01`, `SEM-05`, `SEM-08` | 2, 14, 15, 20, 21: parser/checker and adversarial/property coverage. |
| `KG-AC8` | `KG-C8` | `SEM-08` | 21: formal-proof boundary excludes parser/source completeness. |
| `KG-AC9` | `KG-C9` | `SEM-09` | 20, 30: unified manually dispatched CLI and every relation-family query/context. |
| `KG-AC10` | `KG-C10` | `SEM-06`, `SEM-08`, `SEM-09` | 17–21, 30, 31: two-build equality, profile mapping, add/modify/delete freshness, counts, static checks, no MCP. |
| `KG-N1` | current-turn write scope | `SEM-08` | 1 and completion gate: only this brief is edited; no implementation claim. |
| `KG-N2` | `KG-3`, `KG-C10` | `SEM-08`, `SEM-09` | 16, 17: no MCP or compatibility route. |
| `KG-N3` | `KG-2`, `KG-5` | `SEM-02`, `SEM-03`, `SEM-08` | 5, 13: no parent hand-maintained metadata, duplicate schema, or second store. |
| `KG-N4` | `KG-3`, `KG-7` | `SEM-05`, `SEM-07`, `SEM-08` | 9, 18–21: no fallback, silent loss, or broad-CI shortcut. |
| `KG-N5` | `KG-C`, `KG-C3` | `SEM-01`, `SEM-02`, `SEM-05` | 3, 19, 21: submodule internals excluded; pin/view provenance retained. |
| `KG-N6` | `KG-7`, `KG-C2`, `KG-C6` | `SEM-06`, `SEM-07` | 8, 9, 19: stale/missing/schema/build failures never trigger implicit rebuild. |

## Abstract Design Frame Details

### Responsibility model

The replaceable unit is **parent-owned graph construction and evidence
projection**. It has one controller, one parser boundary, one graph store,
four CLI operations, and all current consumers. The controller owns snapshot
selection, producer invocation, normalization into Graph DSL records, set
reconciliation, SQLite materialization, atomic publication, freshness, query,
and context projection.

AgentCanon owns the generic mechanism and public CLI. The parent owns the
root, source scope, generated SQLite file, and project-specific producer
selection. Existing producers remain owners of the facts they know. No
producer is replaced by graph inference.

### Concept and layer model

1. **Source layer**: one full repository snapshot and authoritative producer outputs.
2. **Scope layer**: `P(S)`, explicit `X(S)`, and derived eligible `U(S)`.
3. **Fact layer**: `D` declarations and `R` observed relations, each with producer, owner, source span/path, and authority.
4. **Graph layer**: `G`, stored using Graph DSL `documents`, `nodes`, `edges`, `diagnostics`, and `metadata`; projections use the existing projection contract.
5. **Projection layer**: `Vp` query/context views, never new source truth.
6. **Review layer**: unresolved, ambiguous, stale, and producer-failure diagnostics returned to the owning tool or workflow.

The dependency direction is `producer -> graph -> consumer`. A consumer may
query or project graph facts but cannot add a fact by parsing the source again.
The runtime dashboard is a source-layer producer whose measurements travel
through metadata and `Vp` context projections; they do not become `D`, `R`, or
an inferred runtime relation.

### Non-goals

- MCP server, MCP registration, or `.codex/config.toml` graph configuration.
- A second dependency parser, line-limited parser, regex/path-or-evidence fact authority, or Python normalized-record decoder.
- R2 scope binding, review binders, byte-level transport envelopes, fixed byte-schema conformance, or a second registry/fingerprint authority.
- Language, compiler, build, configuration, runtime, citation, proof, or PR truth.
- Graph-generated reverse declarations, inferred semantic edges presented as explicit producer facts, or silent deletion of unresolved/ambiguous evidence.
- Splitting the unit into file, finding, or test workstreams.

### Future extension layers

Future layers may add raw runtime observation, dynamic import/call evidence,
proof graphs, or richer semantic projections only after an authoritative producer,
layer contract, provenance fields, and validation route exist. They must attach
to `G` through Graph DSL adapter namespaces and must not alter current `D` or
`R` semantics. A future MCP adapter, if ever approved, is a consumer of the
CLI contract and is outside this design.

### Evaluation axes

| Axis | Required result |
| --- | --- |
| Ownership | Parent path is the only generated graph state; AgentCanon has no parent graph artifact. |
| Authority | Every `D`/`R` edge names its producer and exact source evidence; graph inference is marked separately. |
| Completeness | `P(S) = U(S) ∪ X(S)` with disjoint sets; unresolved and ambiguous sets are explicit and queryable. |
| Freshness | Status distinguishes missing, fresh, stale, incomplete, invalid, and unavailable without implicit rebuild. |
| Publication | Readers observe the previous valid DB or the new valid DB, never a partial candidate. |
| Context fidelity | Every returned item carries owner, source span/path, dependency witness, and producer evidence. |
| Reverse closure | Every stored edge is discoverable through both outgoing and incoming indexes with the same provenance. |
| Reuse | Graph DSL/structured-analysis/semantic-index stores and existing producers remain the only fact sources. |
| Cleanup | R2 transport, binder, duplicate parser, and obsolete giant fixtures/tests have no surviving public route. |

### Canonical-surface relationships

`dependency_manifest.rs::ManifestParser` and `capture_snapshot` are the
dependency-header and source-snapshot authority. `structured_analysis.rs` is
the Graph DSL storage/contract authority. `semantic_index.rs` owns embeddings,
indexed files, and `ContextCell` retrieval evidence. `import_responsibility.py`,
`responsibility_scope.py`, and `scan_code_dependencies.sh` own their observed
relations. `search.py`, `vector_search.py`, `tool_drift.py`,
`check_dependency_headers.py`, and `check_design_doc_claims.py` are consumers.
The graph controller joins these surfaces without copying their semantic
authority. `tools/catalog.yaml`, `agents/skills/catalog.yaml`, and CLI/docs are
public routing views, not alternate implementations.

## Current implementation and reuse survey

The following symbols are current evidence and reuse anchors. The writer must
read the named spans before editing; names in the new design are fixed below.

| Current surface | Current symbols to reuse or retire | Design decision |
| --- | --- | --- |
| `rust/agent-canon/src/dependency_manifest.rs` | `ManifestDirection`, `DependencyKind`, `ManifestDependency`, `ManifestAst`, `DependencyDeclaration`, `SourceIdentity`, `SourceExclusion`, `SurfaceRelation`, `SnapshotHeader`, `SourceUniverse`, `ManifestSnapshot`, `SnapshotRequest`, `ManifestParser`, `capture_snapshot`, `write_snapshot_jsonl`, `normalize_dependency_target`, `scan_manifest_lines`, `contains_manifest_marker`, `write_atomic_with_failure`, `AtomicFailurePoint`, `CandidateCleanup` | Keep source parsing/snapshot concepts; map public graph profile `default` to the current producer profile `parent` before constructing `SnapshotRequest`; make `ManifestParser` read the complete file, remove `HEADER_SCAN_LINES`, delete `contains_manifest_marker` as a pre-parser, and reuse the existing atomic writer/failure seam pattern for graph publication. Delete normalized transport and private R2 symbols. |
| `tools/agent_tools/tool_catalog.py` | `Finding`, `CatalogRow`, `CatalogReport`, `build_parser`, `has_dependency_manifest`, `load_catalog`, `check_entry`, `validate_catalog` | Keep `Finding`, `CatalogRow`, `CatalogReport`, YAML loading, catalog enums, and `validate_catalog` as the `structure-catalog` producer; keep `PublicSurfaceRow`, `PublicSurfaceReport`, and `extract_public_surface` as the separate `public-surface` producer in the same captured artifact. Delete `HEADER_SCAN_LINES` and `has_dependency_manifest`. Replace its five call sites exactly: `load_catalog` (line 177) checks only file existence and YAML mapping; `check_entry` doc/test loops (lines 287 and 299) retain missing-path findings but remove header findings; `load_tool_docs` (line 363) retains TOML kind/list/entry checks but removes the header gate; and `check_tool_docs_manifest` (line 419) retains missing-doc findings but removes the header gate. `ManifestParser`/graph-backed header consumers own dependency-header presence/coverage. Update `tests/agent_tools/test_tool_catalog.py` and catalog docs to assert the replacement. |
| Same Rust file | `NormalizedRecordSet`, `RelationRegistryArtifactV1`, `ObservedEvidence`, `ExtractorCapability`, `Attestation`, `NormalizedRelation`, `AmbiguityA`, `RelationNormalizer`, `read_normalized_record_set`, `ClosureResult`, `AdjacencyProjection` | Delete as transport/fact-authority routes. Their semantic cases move to graph-level unresolved/ambiguous diagnostics where still needed. |
| `rust/agent-canon/src/structured_analysis.rs` | `run`, `run_build`, `run_graph_contract`, `build_structured_analysis_cache`, `collect_documents`, `collect_files`, `initialize_graph_schema`, `has_dependency_manifest`, `dependency_manifest_values`, `dependency_coverage_rules`, and existing `documents`/`nodes`/`edges`/`diagnostics`/`metadata` materialization | Reuse as the Graph DSL store/checker and metadata inventory; remove the dependency-header field extraction and both `HEADER_SCAN_LINES`/`HEADER_SCAN_BYTES` bounds so this module is not a second dependency fact authority. Expose only the narrow crate-private adapter functions needed by `graph.rs`. `initialize_graph_schema` is the current exact symbol; `init_graph_schema` is not a repository symbol. |
| `rust/agent-canon/src/semantic_index.rs` | `ContextPackArgs`, `ContextCell`, `context_pack`, `init_schema`, `open_cache_connection`, `files`, `nodes`, `embeddings` | Reuse the existing semantic-index DB and context-cell evidence; do not copy embeddings into the knowledge graph. |
| `tools/agent_tools/import_responsibility.py` | `Scope`, `ImportRecord`, `ImportCollector`, `Report`, `check_imports`, current JSON output | Remains the responsibility/import-policy diagnostic producer; graph consumes its findings and counts, but does not promote its private `ImportRecord` rows to graph `import` edges because current JSON does not serialize resolved targets. Code relation edges have one authority: `scan_code_dependencies.sh`. No manifest parsing is added. |
| `tools/agent_tools/responsibility_scope.py` | `Scope`, `ImportRule`, `ScopeIndex`, `Finding`, `ScopeReport` | Remains responsibility ownership producer; graph consumes scope/owner evidence. |
| `tools/agent_tools/generate_agent_runtime_dashboard.py` | `AgentRuntimeDashboard`, `RuntimeDashboardSummary`, `HookWorkflowBreakdownReader`, `TokenUsageBreakdownReader`, `SelectionMetricsReader`, `read_candidate_selection_resets`, `render_dashboard_api`, `agent_runtime_dashboard.v1` | Remains the sole runtime evidence/dashboard producer. Repair typed candidate-path rejection and producer-backed measurement capture; graph consumes its API/provenance and never reparses raw logs. |
| `tools/agent_tools/compare_codex_token_footprints.py` / `tools/agent_tools/workflow_monitor.py` | `TokenFootprint`, `parse_token_usage`, `append_monitoring` | Remain the canonical token-event/comparison and monitoring producers; dashboard and graph reuse their output rather than adding a token logger or parser. |
| `tools/agent_tools/vector_search.py` | `Document`, `SearchHit`, `ContextExpansion`, `build_context_expansion`, current `parse_dependency_edges` path | Keep text/call search; delete `strip_manifest_line`, `resolve_dependency_target`, `parse_dependency_edges`, dependency frontier parsing, and use `graph context`. |
| `tools/agent_tools/search.py` | `SearchCorpus.dependency_edges`, `load_corpus`, `header_dependency_hits`, and the direct `vector_search.parse_dependency_edges(request.root, documents)` call | Keep the coordinated-search provider registry, scoring, `ProviderHit`, `Candidate`, and output shape. Delete the direct parser call and load `GraphDependencyFact` rows once through `GraphClient.query(all=True,relation="dependency",direction="both",depth=0)` only when `header-deps` is selected; preserve producer/source/span/evidence references in the existing evidence string and never fall back to source parsing. |
| `tools/agent_tools/search_index.py` | `responsibility_from_text` and its `vector_search.strip_manifest_line` call | Keep indexing/tokenization as a graph consumer; remove manifest-line parsing and obtain owner/dependency fields from graph context/query results. |
| `tools/agent_tools/tool_catalog.py` | `Finding`, `CatalogRow`, `CatalogReport`, `has_dependency_manifest`, `load_catalog`, `validate_catalog` | Keep YAML/catalog validation as the `structure-catalog` producer and emit `PublicSurfaceReport` through the separate `public-surface` producer; remove its bounded marker scan and emit no public fact under `structure-catalog`. It never calls the graph. |
| `tools/agent_tools/check_design_doc_claims.py` | `ClaimTokenClass`, `Claim`, `Finding`, `CheckResult`, `build_parser`, claim cue classification, token rendering | Keep this path only as `GraphClaimConsumer`; delete/replace all ad-hoc parsing, schema/transport decoding, filesystem evidence expansion, and local claim-fact evaluation. It may act only after verified graph integration and obtains path/evidence facts from canonical graph status/query/context. |
| `tools/agent_tools/check_dependency_headers.py` | `build_parser`, `changed_paths`, `should_check`, `DEPENDENCY_HEADERS` output, `HEADER_SCAN_LINES`, `has_dependency_manifest`, `has_dependency_header`, `strip_manifest_line`, `manifest_lines`, `allowed_contract_kinds`, and `contract_kind_findings` | Retain path selection and the established pass/fail label. Delete every parser/line-limit/registry-decoder symbol named here; after verified `GraphClient.status()`, obtain `manifest.present`, `manifest.contract`, and `manifest.responsibility` items from `GraphClient.context()` for each selected path. The manifest producer, not this checker, validates the registry. |
| `tools/agent_tools/tool_drift.py` | `ManifestEdge`, `has_dependency_manifest`, `strip_manifest_line`, `repo_relative`, `normalize_target`, `manifest_edges`, `HEADER_SCAN_LINES`, `MANIFEST_FIELD_COUNT`, `MANIFEST_REASON_MAX_SPLIT`, `check_catalog_entries`, `check_link`, `run_checks`, and the `os` import | Delete `ManifestEdge` and every named parser/normalizer/line-limit constant or function, including `repo_relative`; its only callers are the deleted `normalize_target` and `manifest_edges`, so delete the now-unused `os` import as well. Retain contract/link/text/catalog drift policy and finding formats; `run_checks` obtains one canonical `GraphDependencyFact` tuple from `GraphClient.query(all=True,relation="dependency",direction="both",depth=0)` and passes it to retained link/reverse-kind logic. Delete only `check_catalog_entries`'s local `missing-dependency-header` branch; the graph-backed dependency-header checker owns that oracle. |
| `tools/agent_tools/dependency_manifest_records.py` | `load_normalized_record_set`, `ValidatedRelationRegistryV1`, `_validate_*`, `write_relation_registry_conformance_artifact` | Delete the duplicate Python transport decoder/projector and registry producer. |
| `tools/agent_tools/bind_r2_scope.py` | `manifest`, `closeout`, `MANIFEST_VERSION`, `CLOSEOUT_VERSION` | Delete; review artifacts are not graph inputs. |

### Dependency and library reuse survey

The Rust crate inventory is `rust/agent-canon/Cargo.toml` and its locked
`Cargo.lock`: `serde_json` for fixed JSON, `sha2` for existing fingerprints,
`rusqlite` with the existing `bundled` feature for Graph DSL SQLite, and
`yaml-rust2` for existing catalog/config parsing. The Python route already
uses repository-approved standard-library `argparse`, `json`, `pathlib`, and
`subprocess`, plus its existing YAML/TOML dependencies; the shell producer uses
the existing POSIX/Git/coreutils toolchain. No Cargo, Python, or shell
dependency manifest changes are authorized, and no new library is needed.
The new graph controller, GraphClient, candidate lifecycle, BFS closure, and
schema validation must use these installed dependencies and existing helpers;
adding a serializer, graph database, subprocess framework, or parser library
is a design blocker requiring a revised source packet and review.

The reuse basis is deliberately narrow: Graph DSL supplies storage and
representation checks, structured-analysis supplies document/graph inventory,
semantic-index supplies retrieval cells, and existing tools supply facts. The
new controller supplies orchestration and joins only.

## Mathematical and evidence contract

For one immutable repository snapshot `S` and selected producer profile `p`:

The symbols used by the contract and producer matrix are fixed here before
their first relation/schema use: `RepoPath` is a normalized parent-root-
relative path; `X_R(S,p)` is a relation-level explicit exclusion record with
producer, rule, and reason; `RelationKind` is the closed persisted enum
`dependency|owner|scope|import|include|symbol|call|containment|document|catalog|pin|view|generated|submodule|public`;
`SourceSpan` is `{path:RepoPath,start_line:u64,start_column:u64,end_line:u64,end_column:u64}`;
`ProducerArtifact` is
`{producer_id:string,version:string,command:string,root:RepoPath,content_sha256:Hex64,relation_families:[RelationKind],artifact_ref:string}`;
and `DependencyWitness` is
`{edge_id:string,relation:RelationKind,from:RepoPath,to:RepoPath,owner:string|null,source_path:RepoPath,source_span:SourceSpan|null,producer:string,evidence_ref:string,authority:string}`.
`GraphContextItem` is
`{kind:string,value:string,source_store:string,producer:string|null,source_path:RepoPath|null,source_span:SourceSpan|null,evidence_ref:string|null,authority:string,rank:u64|null,score:f64|null,bucket:string|null,excerpt:string|null,cache_state:SemanticIndexState|null}`;
its `source_store` is one of `graph|manifest|responsibility|code-dependencies|structured-analysis|semantic-index|runtime-dashboard`, and every item is sorted by `(kind,source_store,source_path,evidence_ref,value)`.
`DurableGraphState` is
`fresh|missing|stale|incomplete|invalid|schema-mismatch|unavailable`, and
public `GraphStatusCode` additionally admits `build-failed|publication-failed` for
operation results. The later CLI section repeats these as machine-readable
schemas, not alternate definitions.

- `P(S)` is every candidate path/source node enumerated by the authoritative snapshot producer, including paths later excluded.
- `X(S)` is the explicit exclusion set with a producer/rule and reason for each member.
- `U(S) = P(S) \ X(S)` is the eligible graph universe. The build must record `P(S) = U(S) ∪ X(S)` and `U(S) ∩ X(S) = ∅`.
- `D` is the set of typed dependency declarations returned by the one `ManifestParser` and normalized only for graph joins.
- `O` is the set of raw owner/import/source/cross-file/public relations emitted by supported extractors with extractor provenance; it includes observations that reconcile against or differ from `D`.
- `R` is the accepted authoritative relation set after producer validation and relation-family reconciliation. Graph inference is not in `R`; derived reverse/containment projections are marked separately.
- `G` is the Graph DSL materialization of source records, `U`, `D`, `R`, provenance, diagnostics, and projections.
- `Vp` is the profile-specific projection selected from `G`; `members(Vp) ⊆ members(G)`.
- `Uncovered(S,p)` contains every eligible source/relation obligation required by the selected profile for which no producer declaration or observation joins to `D`/`R`, and which is not explicitly in `X(S)`, `X_R`, `Unresolved`, or `Ambiguous`. It is a coverage gap, not a guessed edge.
- `Unresolved(S,p)` contains every source, target, owner, producer, or relation required by the selected profile that cannot be resolved from `P`, `U`, `D`, `R`, or an authoritative producer result.
- `Ambiguous(S,p)` contains every item with multiple candidate owners, sources, targets, relation kinds, or producer interpretations that the authoritative tools do not resolve. Let `A = Unresolved(S,p) ∪ Ambiguous(S,p)` for coverage accounting; neither member of `A` is covered.

Materialization is lossless for required explicit facts:
`V(G) = normalize(U(S) \ X(S))`, `G_sources = V(G)`,
`G_exclusions = X(S)`, `D_repr(G) = D`, `O_repr(G) = O`, and
`G_explicit^R = R`; producer records that do not belong to one of these sets
are not silently dropped. The projection equality is
`Vp = π_p(G)` and
`members(Vp) = {g ∈ members(G) | profile_p(g) = true}`. A required producer
record that cannot join to `P(S)`, `U(S)`, a declaration, or a source span is
added to `Unresolved(S,p)` with code `producer.record_unjoinable`; a record
with more than one authoritative join is added to `Ambiguous(S,p)` with code
`producer.record_ambiguous`. A record filtered by an explicit `X(S)` rule is
represented in `G_exclusions` with its exclusion reason and is not unresolved.
For every comparable relation family, `O \ D` and `D \ O` are persisted as
reconciliation findings with family, producer, source span, and reason. The
coverage numerator excludes `X(S)`, `X_R`, `A`, and `Uncovered`; none is
counted as covered, complete, or resolved. `Uncovered` is persisted in
`diagnostics` and the status/query/context arrays with its obligation source,
producer profile, and missing-join reason; its count uses the same lexical
`(code,path,reason)` ordering as the other diagnostic sets.

Notation is separated by level: `X(S)` is reserved for excluded source paths;
relation-level exclusions are `X_R(S,p)` records with producer/rule/reason.
`Unresolved(S,p)`, `Ambiguous(S,p)`, and `Uncovered(S,p)` are the completeness
diagnostic sets; `A` is only the union of the first two for equations, never a
record type. A missing
relation target is `Unresolved`, an explicitly unsupported relation is `X_R`,
and a multiple authoritative join is `Ambiguous`. Malformed producer output is
an operation `invalid`/`build-failed` and is never inserted into `G`. Thus
`unresolved_count=|Unresolved|`, `ambiguous_count=|Ambiguous|`, and
`excluded_count=|X(S)|+|X_R|`, with each array carrying a `source|relation`
scope tag. Only `U(S)`, resolved `D`, and accepted `R` contribute to coverage.

`P(S)` is formed from the authoritative `capture_snapshot` path inventory, not
by re-running a different path enumeration in a consumer. The snapshot includes
tracked, untracked, added, modified, and deleted path records with normalized
parent-relative slash paths; a deleted path has no scanner content and is kept as
an explicit `Unresolved` source record with `source.deleted`, so deletion cannot
silently reduce the universe. `X(S)` records only explicit graph-source rules:
generated outputs, duplicate canonical/view identities, and AgentCanon
submodule internals; scanner-unsupported suffixes are relation-level `X_R`, not
source exclusions;
the submodule pin and parent root/view relation remain provenance rows.
Runtime evidence result prefixes are explicit `X(S)` with
`source.excluded_runtime_result`, owner `result-artifact-writeout`/
`agent-log-analysis`, and producer `source-snapshot`: `.agent-canon/log-archive/**`,
`reports/agent-runtime-dashboard/**`, and
`experiments/_template/result/readonly_agent_log_analysis_*/**` are consumed
read-only by the `runtime-dashboard` producer and are never promoted as source
or dependency facts. This covers those four directories when present in a
parent checkout and does not require creating them when absent. Their bytes
remain user-owned and preserved; their hashes enter runtime producer
provenance, not `P(S)` source coverage. Define
The scanner suffix set is exactly the case-sensitive set
`{.py,.c,.cc,.cpp,.h,.hpp,.sh,.bash,.zsh}`. Its graph input is exactly
`--paths-file <candidate-temp>/scanner-paths.txt`, a sorted UTF-8 newline list
that may be empty; a missing file is failure, and an empty file must produce
`CODE_DEPENDENCY_SCAN=pass files=0` without `git ls-files` fallback. Define
`P_scan = {p ∈ U(S) | p is an existing regular non-symlink file and p has one of
the scanner suffixes}`. A path with a suffix outside the scanner suffix set is
not globally excluded: Markdown, Rust, TOML, YAML, and other eligible files
remain in `U(S)` for document, structure, catalog, public-surface, or other
authoritative producers. Only the code-dependency relation obligation for such
a path is `X_R` with `scanner.unsupported_suffix`; it is not `X(S)` and cannot
reduce graph completeness for another producer. The graph writes the sorted,
normalized `P_scan` paths to
the explicit `--paths-file <candidate-temp>/scanner-paths.txt` input; the scanner
is never allowed to fall back to its internal `git ls-files` enumeration for a
default graph build. Its completion marker must equal `|P_scan|`. Every path in
`P(S) \ P_scan` is classified before the scanner: an explicit graph-source
exclusion carries `source.excluded` and is counted in `X(S)`; a non-scanner but
eligible path has no code-scanner obligation and remains available to its
owning producer; a deleted path in `U(S)` carries `source.deleted` as
`Unresolved`; an eligible but unreadable/non-regular path in `U(S)` carries
`source.unreadable` as `Unresolved`. There is no
`source.excluded` diagnostic for a path that remains in `U(S)`, so scanner-level
noncoverage cannot be confused with the mathematical exclusion set. This closes
scanner coverage over the same `P(S)` snapshot used for `D` and freshness.

The identity function normalizes canonical/view aliases once, so
`V(G)=normalize(U\X)` has no duplicate logical identity. Normalization is fixed:
first resolve a path to the parent-relative slash form, reject absolute or
`..`-escaping paths as `Unresolved`, then apply the structure producer's
canonical/view map. A canonical path owns `logical_id=canonical:<path>`; a view or
root alias owns the same canonical ID and stores `view_path=<path>`; generated
paths use `logical_id=generated:<path>` and are excluded unless the structure
producer marks them as a source. If the authoritative map has two targets, emit
`Ambiguous(identity.multiple_canonical_targets)` and publish no relation for that
identity. If a canonical record and a view record otherwise collide, retain the
canonical record, retain the view-to-canonical provenance edge, and put the
duplicate view source in `X(S)` with `identity.canonical_precedence`; this is not
a worker-selected tie-break. All other same-ID collisions are `Ambiguous`, never
lexicographic deduplication. Graph metadata stores
the parent `HEAD`, dirty-state fingerprint, per-source content hashes,
AgentCanon submodule pin, root/view mapping, Graph DSL schema version, producer
tool/version fingerprints, and build input fingerprint. These fields are
freshness inputs or provenance, not graph-owned language/compiler/config facts.

The profile is complete only when the scope equations hold, every required
record has producer provenance, every projection member joins to `G`, and
`Unresolved(S,p) = Ambiguous(S,p) = Uncovered(S,p) = ∅`. Otherwise the graph
remains published but status is `incomplete`; all three sets are returned and
query/context refuse facts while preserving their diagnostics. Existing reverse
edge migration debt is not silently counted as completeness.

### Runtime evidence producer and repair contract

Runtime measurements are a broad evidence lane in this graph unit, but they
are not a new graph semantic relation and are never inferred by `graph.rs`.
The sole runtime producer is
`tools/agent_tools/generate_agent_runtime_dashboard.py::AgentRuntimeDashboard`
and its existing `render_dashboard_api` output, schema
`agent_runtime_dashboard.v1`. It reuses
`HookWorkflowBreakdownReader`, `TokenUsageBreakdownReader`,
`SelectionMetricsReader`, `WaveExecutionBreakdownReader`,
`compare_codex_token_footprints.py::TokenFootprint`, and
`workflow_monitor.py::append_monitoring`; no second logger, event stream, or
runtime-measurement schema is created. Graph build invokes the dashboard once
with its existing structured API output in the candidate, records that output
as a `ProducerArtifact`, and promotes only its typed measurements and
diagnostics into context/provenance. The graph does not parse raw hook JSONL,
workflow Markdown, or token sessions a second time.

The dashboard API's one canonical `runtime_measurements` row has exactly
`RuntimeMeasurement` fields declared above. The field source mapping is fixed:
`responsibility_unit_id` comes from the run-bundle/task packet identity emitted
by `tools/agent_tools/workflow_monitor.py::append_monitoring` and the matching
hook `codex_trace_key`; `generation_parent` and `reuse_mode` come from the
existing subagent-wave `parent_or_delegate` and reuse markers in that same
`workflow_monitoring.md`; `packet_hash` is the existing packet/artifact
fingerprint recorded by the run-bundle producer; `context_bytes_by_source`
comes from producer source-packet byte counts keyed by canonical source ID;
`finding_iteration` and `review_iteration` come from existing finding/review
ledger rows; `writer_ids` and `reviewer_ids` come from existing role/instance
and review records; `launch_epoch` and `finish_epoch` come from run-bundle
lifecycle timestamps; `input_tokens`, `cached_input_tokens`, `output_tokens`,
and `reasoning_tokens` come from
`compare_codex_token_footprints.py::TokenFootprint` fields
`input_tokens`, `cached_input_tokens`, `output_tokens`, and
`reasoning_output_tokens`; `retries`, `waits`, and `progress_bytes` come from
canonical lifecycle/progress entries; and `repeated_artifact_hashes` is
computed from the canonical artifact hash field before dashboard aggregation.
Each value is read through its named existing producer, never by matching
free-form text in the graph. `responsibility_unit_id` is the
canonical run/packet responsibility identity; `generation_parent` is the
literal parent packet or generated-artifact identity when present;
`reuse_mode` is the producer's existing reuse classification; `packet_hash` is
the hash of the immutable packet bytes; `context_bytes_by_source` is a sorted
map of canonical source IDs to context bytes; `finding_iteration` and
`review_iteration` are producer-recorded counters; `writer_ids` and
`reviewer_ids` are sorted unique canonical role/instance IDs; launch/finish
are epoch milliseconds; token fields are the producer's input, cached-input,
output, and reasoning-output (`TokenFootprint.reasoning_output_tokens` maps to
`RuntimeMeasurement.reasoning_tokens`) counts; retries, waits, and progress bytes are
the recorded totals; and `repeated_artifact_hashes` contains sorted hashes
that occurred more than once. Missing optional producer fields stay `null`,
while an observed zero retry/wait/progress count stays `0`; graph never
substitutes a zero for missing evidence.

The implementation mapping is one-to-one and has no worker choice:

| RuntimeMeasurement field(s) | Canonical producer field/artifact | Cardinality and missing rule |
| --- | --- | --- |
| `responsibility_unit_id`, `generation_parent`, `reuse_mode`, `packet_hash` | Existing `workflow_monitor.py::MonitoringEntries` run-bundle identity/reuse fields and the packet/artifact fingerprint emitted by that bundle | Exactly one row per responsibility unit; identity is required, parent/reuse/hash are `null` when not emitted. |
| `context_bytes_by_source` | Existing source-packet entries keyed by producer source ID and their UTF-8 byte counts | Sorted map; an absent source has no key, not an invented zero-valued source. |
| `finding_iteration`, `review_iteration` | Existing finding/review ledger rows consumed by the runtime dashboard | One maximum observed counter per unit; absent is `null`, and an explicit producer zero remains `0`. |
| `writer_ids`, `reviewer_ids` | Existing run-bundle role/instance and review records | Sorted unique lists; absent is an empty collection, never a guessed actor. |
| `launch_epoch`, `finish_epoch` | Existing run-bundle lifecycle timestamps | One timestamp each; absent is `null`, and finish-before-launch is a typed dashboard diagnostic. |
| `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens` | `compare_codex_token_footprints.py::TokenFootprint.{input_tokens,cached_input_tokens,output_tokens,reasoning_output_tokens}` | One footprint per compared unit; absent comparison is `null`, an emitted zero remains `0`, and only the graph projection renames `reasoning_output_tokens`. |
| `retries`, `waits`, `progress_bytes`, `repeated_artifact_hashes` | Existing lifecycle/progress/retry/wait events plus canonical artifact hashes read by `workflow_monitor.py::append_monitoring` | Totals are `0` only when explicitly counted; missing totals remain `null` in the producer row; repeated hashes are sorted unique hashes with count greater than one. |

`workflow_monitor.py::MonitoringEntries` is extended with these exact typed
fields: `responsibility_unit_id: str`, `codex_trace_key: str | None`,
`generation_parent: str | None`, `reuse_mode: str | None`,
`packet_hash: str | None`,
`context_bytes_by_source: tuple[tuple[str,int], ...]`,
`finding_iteration: int | None`, `review_iteration: int | None`,
`writer_ids: tuple[str, ...]`, `reviewer_ids: tuple[str, ...]`,
`launch_epoch: int | None`, `finish_epoch: int | None`,
`retries: int | None`, `waits: int | None`, `progress_bytes: int | None`,
`token_footprint_ref: str | None`, and
`artifact_hashes: tuple[str, ...]`. `codex_trace_key` is copied from the
existing hook environment/payload field and is the only join key to the hook
JSONL namespace; it is not a new identifier. The existing `signals` section receives
one canonical JSON object under key `runtime_measurement_input` with exactly
those snake-case keys; map/list values are sorted and optional values are JSON
`null`, while explicit numeric zero remains `0`. Token counts are deliberately
not copied into this lifecycle record: `token_footprint_ref` is joined to the
canonical `TokenFootprint`, and `artifact_hashes` is reduced to repeated hashes
by the dashboard. Thus `RuntimeMeasurement` is the one dashboard API schema,
not a second logger or transport schema.
`workflow_monitor.py::append_monitoring` remains the lock and write owner; no
new logger, JSON schema, or artifact family is introduced. The dashboard joins that record to `TokenFootprint` by
`responsibility_unit_id` and to the hook log by `codex_trace_key`; a missing
join produces a typed diagnostic and does not synthesize a measurement row.
The source fixtures are the existing runtime-dashboard, token-footprint, and
workflow-monitor fixtures, extended with one complete row, one missing-
optional row, one explicit-zero row, and the measured 2,028-entry attribution
baseline before graph consumer tests.

`read_candidate_selection_resets` gets event-derived candidate paths only
through this typed normalization boundary:
`RuntimePathResolution = {accepted:Vec<RepoPath>,rejected:Vec<GraphDiagnostic>}`.
For each raw candidate, accept only a UTF-8 string or `Path` that is
root-relative, slash-separated, nonempty, has no NUL, no absolute or drive
prefix, no `..` component, and normalizes away `.` components to a nonempty
`RepoPath`; verify the resolved path remains under the canonical root and is a
regular non-symlink source before calling `git log`. Reject, without probing
Git, with these stable `GraphDiagnostic.code` values:
`runtime.path.type`, `runtime.path.empty`, `runtime.path.absolute`,
`runtime.path.drive_prefix`, `runtime.path.parent_escape`,
`runtime.path.nul`, `runtime.path.separator`, `runtime.path.root_escape`, or
`runtime.path.non_regular`. A rejection carries `set=Unresolved`,
`producer=generate_agent_runtime_dashboard.py`, the responsible unit/name,
and `evidence_ref=runtime-dashboard:<event-id>`; raw malformed text is kept
only in a bounded reason string and is never converted into `RepoPath`.
`read_candidate_selection_resets` returns accepted resets plus the typed
rejection list, and the existing `agent_runtime_dashboard.v1` API exposes that
same `selection_path_rejections` array. The graph adapter reuses those exact
diagnostics into `GraphContextResult.context_diagnostics`; they do not enter
the graph completeness arrays, and it does not define a parallel path-error
schema.
The only API extension is therefore the existing dashboard payload with
`runtime_measurements:[RuntimeMeasurement]` and
`selection_path_rejections:[GraphDiagnostic]`; the schema identifier remains
`agent_runtime_dashboard.v1`, and all other dashboard fields retain their
current names and meaning.

Workflow attribution has one exact writer owner:
`.codex/hooks/skill_usage_logger.py::append_skill_usage_entry` constructs the
canonical `candidate_workflows`, `selected_workflow`, `selected_workflows`,
`workflow`, and `workflow_family` fields, and
`.codex/hooks/hook_event_log.py::HookLogContext.append` is the shared append
boundary that preserves those fields and their `hook_log_namespace` in the
same JSONL event. This graph unit expands the existing skill logger's
workflow-context enrichment to every hook event it writes; no dashboard or
graph code assigns a workflow. The exact baseline is the hook JSONL set
resolved by `runtime_log_paths.py::hook_results_dir` and consumed by
`HookWorkflowBreakdownReader.read`; its generated API artifact records
`entries_without_workflow=2028` and diagnostic
`runtime.workflow_attribution_missing` with
`artifact_ref=producer:runtime-dashboard/runtime-dashboard.json#sha256=<Hex64>`.
The dashboard reader owns counting and reporting, not attribution authority. A missing field
never becomes a guessed workflow: namespace-local carry-forward remains
explicitly `context_attributed_entries`, while the remaining count is
`entries_without_workflow`. The observed baseline of 2,028 missing hook
entries is retained as a measured `runtime.workflow_attribution_missing`
diagnostic and as the breakdown count; repair changes the hook owner and
re-runs the dashboard, not the graph parser.

Token comparison is owned by `compare_codex_token_footprints.py` and its
existing workflow-monitor evidence. `TokenUsageBreakdownReader` consumes the
canonical producer output/artifact rather than maintaining a second regex
fact authority. The observed `comparison_count=0` remains a measured zero and
emits `runtime.token_comparison_missing` with the exact producer/report
references; it is not silently interpreted as token savings or as evidence
that the feature is unsupported. Dashboard API fields, graph context
`runtime_measurements`, and diagnostics all preserve the distinction between
missing, zero, and present values.

Runtime diagnostic classification is fixed: rejected event paths are
`set=Unresolved,severity=Warn`; missing workflow attribution is
`set=Uncovered,severity=Warn,code=runtime.workflow_attribution_missing`; a
missing token comparison is
`set=Uncovered,severity=Warn,code=runtime.token_comparison_missing`; and a
missing join is `code=runtime.measurement_join_missing,set=Unresolved,severity=Warn`;
invalid lifecycle ordering is
`code=runtime.lifecycle_order,set=Ambiguous,severity=Warn`. These runtime
diagnostics are returned in `GraphContextResult.context_diagnostics` and the
producer artifact, but do not enter `R`, `U(S)`, `D`, or the graph completeness counts because
they have no `RelationKind`; graph completeness remains governed only by the
mathematical sets in the graph contract. A malformed dashboard API or failed
canonical producer is instead `GraphError::Producer` and prevents publication.

The runtime lane is attached to the graph as producer metadata and
`GraphContextItem{source_store="runtime-dashboard"}` projections plus typed
diagnostics. It adds no `RelationKind`, no language/compiler/config/runtime
truth, and no duplicate logger or schema. `context` returns the exact
measurement row selected by `responsibility_unit_id` together with its
producer, packet/artifact hashes, source references, and diagnostic state.

### Producer symbol declarations

The public-surface producer symbols are fixed before any producer table or
relation matrix refers to them. `RepoPath` means a normalized parent-relative
slash path. `CachePath` is a canonical UTF-8 string with exactly one of these
forms: the generated semantic-index path is `cache:<repo-key>/<name>`, while
an explicit cache outside the semantic-index home is the normalized absolute
path itself; neither form is ever coerced to `RepoPath`. `repo-key` reuses
`semantic_index.rs::repo_cache_key`: canonicalize the parent root, take its
final component, replace every character outside `[A-Za-z0-9_-]` with `-`,
trim `-` (fall back to `repo`), append `-` plus the first eight bytes of the
lowercase SHA-256 of the canonical root path, and use that exact string. `name`
is a slash-normalized relative UTF-8 path with nonempty components, no `.` or
`..`, and only `[A-Za-z0-9._/-]`; the default is `index.sqlite`. The resolver
reuses `semantic_index::default_db_path` and
`AGENT_CANON_SEMANTIC_INDEX_HOME`/`HOME` selection. It emits the `cache:` form
for the resolved generated path (including an environment override) and the
absolute form when the internal semantic-index caller supplies an explicit
`--db` path; this is not a graph CLI option and never changes the fixed graph
DB path. Existing paths are
`fs::canonicalize`d, while missing paths use lexical absolute normalization.
The environment override changes only cache resolution, never graph authority,
and is recorded as semantic-index availability metadata. `CachePath` is never
used for the parent-owned graph DB;
`SourceSpan` means
`{path:RepoPath,start_line:u64,start_column:u64,end_line:u64,end_column:u64}`.
In `tools/agent_tools/tool_catalog.py`, `PublicSurfaceReport.rows` is sorted by
`(kind,surface_id,path,start_line)` and `authority` is always
`public-surface`. The existing catalog symbols remain unchanged. These are the
only public-fact extraction interfaces available to `graph.rs`.

### Version-one producer profile

`p` is not an open-ended configuration surface. Version one has exactly one
profile, `default`; omitting `--profile` means `default`, and any other value
is an invalid command argument. The parent selects the root, not a custom
producer list. The fixed profile is:

The profile adapter is exact and one-way:
`graph.rs::snapshot_profile_for_graph("default") -> Ok("parent")`; every other
public value returns `GraphError::Usage` and exit `2`, including the internal
producer word `parent`. `run_build` resolves the parent root and candidate
directory first, then constructs the existing record exactly as
`SnapshotRequest {root:<resolved-parent-root>, profile:"parent".into(),
output_jsonl:<candidate>/producer-artifacts/source-snapshot/source-snapshot.jsonl}`.
It calls `capture_snapshot(&request)`, requires
`dependency_manifest::snapshot_profile(&snapshot)=="parent"`, and writes the
captured bytes through the existing `write_snapshot_jsonl`, made
`pub(crate)`, before hashing. The source producer's logical
`ProducerArtifact.command` is exactly
`dependency_manifest::capture_snapshot graph-profile=default profile=parent`;
its artifact reference supplies the output identity. An omitted public
profile and explicit `--profile default` therefore construct the same request
and fingerprint. No caller can select a different producer profile.

| Producer ID | Current owner and invocation | Graph contribution | Failure rule |
| --- | --- | --- | --- |
| `source-snapshot` | `dependency_manifest::capture_snapshot` through `ManifestParser`, with public graph profile `default` mapped exactly to `SnapshotRequest.profile="parent"` and `SnapshotRequest.root=<resolved-parent-root>` | `P(S)`, `X(S)`, `U(S)`, source identity, Git/content snapshot; producer metadata records `graph_profile=default` and `source_snapshot_profile=parent` | Required; build fails without publishing, including any request/header profile mismatch. |
| `structure-catalog` | `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/repo_structure_contract.py --root <parent-root> --contract <parent-root>/vendor/agent-canon/documents/repo-structure-contract.toml --format json` plus `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/tool_catalog.py --root <parent-root> --format json`, both with `cwd=<parent-root>` | canonical/view/generated/submodule mapping, catalog relations, pin/view provenance, and structure diagnostics | Required; build fails without publishing when the parent boundary cannot be classified. |
| `public-surface` | `tool_catalog.py::extract_public_surface(<parent-root>)`, emitted in the same `tool_catalog.py --root <parent-root> --format json` artifact with `cwd=<parent-root>` | complete public CLI/skill/tool relations from the token-parsed manual dispatch in `main.rs` and `graph.rs`, `CLI_ENTRYPOINTS.md`, `tools/catalog.yaml`, and `agents/skills/catalog.yaml` | Required; missing/ambiguous extraction or a public row without source span is `build-failed`, never an inferred graph fact. |
| `structured-analysis` | `<parent-root>/vendor/agent-canon/tools/bin/agent-canon structured-analysis document-inventory --root <parent-root> --json-out <candidate-temp>/document-inventory.json --markdown-out <candidate-temp>/document-inventory.md`, `cwd=<parent-root>` | document metadata, containment/document relations, and diagnostics; it is not the owner/scope authority | Required; build fails without publishing. The two temporary outputs are read, hashed, and removed before publication. |
| `responsibility-scope` | `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/responsibility_scope.py --root <parent-root> --format json`, `cwd=<parent-root>` | owner/scope mapping for source and public surfaces | Required; build fails without publishing. |
| `import-responsibility` | `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/import_responsibility.py --root <parent-root> --format json`, `cwd=<parent-root>` | responsibility/import-policy diagnostics, counts, and producer evidence; not graph `import` edges | Required for policy diagnostics; build fails without publishing when its JSON cannot be captured. Its valid findings do not create `R`. |
| `code-dependencies` | `bash <parent-root>/vendor/agent-canon/tools/agent_tools/scan_code_dependencies.sh --root <parent-root> --print-unresolved --paths-file <candidate-temp>/scanner-paths.txt`, `cwd=<parent-root>` | sole code relation producer: Python `import`/`from-import-symbol`, C-family `include`, and shell `source` rows | Required; build fails without publishing. |
| `semantic-index` | `semantic_index::default_db_path(root)` at `~/.cache/agent-canon/semantic-index/<repo-key>/index.sqlite`, or `AGENT_CANON_SEMANTIC_INDEX_HOME` override | retrieval/context evidence only; never `D` or explicit `R` authority | Optional for build; absence is an explicit context-unavailable diagnostic. |
| `runtime-dashboard` | `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/generate_agent_runtime_dashboard.py --root <parent-root> --out <candidate-temp>/runtime-dashboard.md --api-out <candidate-temp>/runtime-dashboard.json`, `cwd=<parent-root>` | measured runtime evidence, workflow-attribution/token/path diagnostics, and `RuntimeMeasurement` context projections; no `RelationKind` or language/runtime truth | Required for the broad runtime-evidence profile; malformed API or producer failure aborts graph publication. |

The exact `code-dependencies` capture is a `Command` with executable `bash`,
arguments `[<parent-root>/vendor/agent-canon/tools/agent_tools/scan_code_dependencies.sh,
--root, <parent-root>, --print-unresolved, --paths-file,
<candidate-temp>/scanner-paths.txt]`, and `cwd=<parent-root>`. The UTF-8
`scanner-paths.txt` contains the complete sorted `P_scan` list, one normalized
path per line, and may be empty. The graph always supplies this explicit file;
the scanner adds `--paths-file` as a closed input mode, rejects a missing file,
and does not fall back to `git ls-files` when the file has zero lines. This
eliminates argument-length assumptions and keeps the no-line-limit contract.
The graph captures stdout and stderr to candidate-temporary files and hashes the complete
stdout artifact. It accepts only tab-separated lines beginning
`CODE_DEPENDENCY` with exactly seven fields
`CODE_DEPENDENCY,language,kind,source,target,symbol,raw`; an empty target is an
explicit `Unresolved` record with `scanner.target_unresolved` because
`--print-unresolved` is required. The final
nonempty line must be exactly `CODE_DEPENDENCY_SCAN=pass files=<decimal>`;
that line is a completion marker, not a relation. `CODE_DEPENDENCY` is an
exact field equality, not a prefix; fields contain no NUL, newline, or tab and
the `raw` field has no escaping convention, so a tab in raw source is a
malformed record. The decimal marker count must equal the number of eligible,
non-symlink scanner paths in `P(S)` whose normalized repository path ends in
exactly one of `.py`, `.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.sh`, `.bash`, or
`.zsh`; suffix matching is case-sensitive and paths are slash-normalized
relative to `<parent-root>`; this set is definitionally `P_scan`, so the marker
must be exactly `files=|P_scan|` and is not the number of emitted edges. Any other nonempty
line, malformed record, missing completion marker, marker-count mismatch, or
nonzero process exit is a producer failure: `graph build` returns
`build-failed` and publishes nothing, while `status`, `query`, and `context`
return `build-failed` with the reason and empty evidence projections. No
trailing status line or stderr text is parsed as a fact.

The scanner-kind normalization is fixed: `python/import` becomes
`RelationKind=import`; `python/from-import-symbol` becomes `symbol`;
`c-family/include` becomes `include`; and `shell/source` becomes `include`
with `language=shell` and the original `kind=source` retained in provenance.
No other language/kind pair is promoted to `R`; it becomes `X_R` with
`scanner.unsupported_kind` and contributes to `excluded_count`. `import-responsibility.py` findings remain a
separate policy-diagnostic producer, so there is no second Python import edge
authority. The graph adds one capability diagnostic
`call=unsupported:producer=code-dependencies` for the default profile; this
is the authoritative `X_R` record for call queries and is not a guessed edge or a
fabricated scanner line.

Each required producer returns its existing machine-readable output plus command,
producer ID, producer version, root, and content hash in the build's metadata.
The graph validates the output shape and joins it by repository path/source
span; it does not reparse producer text. Producer stdout/TSV and the temporary
structured-analysis JSON are captured as in-memory or candidate-temporary
artifacts, hashed, and deleted before `graph.sqlite` is published; no producer
artifact becomes a second durable graph store. A producer error aborts the
candidate before publication. For `graph build`, all structured-analysis output
paths are under the candidate temporary directory. For `status`, the same
producer command runs with `--json-out <status-temp>/document-inventory.json`
and `--markdown-out <status-temp>/document-inventory.md` in a fresh OS
temporary directory, which is removed by a finally/RAII cleanup path; producer
execution is therefore read-only with respect to the parent checkout and fixed
DB. Future profiles require a new design review and
may not silently alter `default`.

Relation-family ownership is closed for version one:

| Relation family | Producer ID(s) and exact source | Evidence promoted to `O`/`R` |
| --- | --- | --- |
| `dependency` | `source-snapshot`: `ManifestParser::parse`/`capture_snapshot` | `D`, declaration span, resolved target, declaration kind, parser version. |
| `owner` / `scope` | `responsibility-scope` only: `responsibility_scope.py` `ScopeReport` JSON | owner path, scope rule, responsibility source span; structured-analysis metadata may join the path but cannot author this relation family. |
| `import` / `include` / `symbol` / `call` | `code-dependencies` only: `scan_code_dependencies.sh` TSV; `import-responsibility` remains policy diagnostics only | extractor relation, source/target path, raw producer line, extractor version, supported/unsupported classification. |
| `containment` / `document` | `structured-analysis`: `document-inventory` JSON; Graph DSL document/node rows | document/file containment, document relation, inventory source span and artifact hash. |
| `catalog` | `structure-catalog`: `repo_structure_contract.py` JSON plus `tool_catalog.py --root <parent-root> --format json` | catalog entry/path, catalog source span, and validation finding. |
| `public` | `public-surface`: `tool_catalog.py::extract_public_surface`, reading existing `rust/agent-canon/src/main.rs` dispatch, `agents/canonical/CLI_ENTRYPOINTS.md`, `tools/catalog.yaml`, and `agents/skills/catalog.yaml` | public CLI/skill/tool relation, primary/secondary source spans, parser version, and validation finding. `tool_catalog.py` must emit sorted `PublicSurfaceRow{surface_id,kind,path,selector,source_span,secondary_spans,authority}` rows; no graph code reparses these sources. |
| `pin` / `view` / `generated` / `submodule` | Primary authority is `source-snapshot` for `pin` and `submodule`; primary authority is `structure-catalog` for `view` and `generated`. The other producer may supply only a named secondary provenance artifact. | parent/root-view identity, AgentCanon pin, generated/excluded reason; submodule internals remain `X`. |

Every row is tagged with exactly one producer ID and relation family. A family
that a producer cannot support produces an explicit `X_R`, `Unresolved`, or
`Ambiguous` record rather than an inferred relation. `check_dependency_graph.sh` and
`run_repo_dependency_review.sh` consume these captured rows; they never invoke
`scan_code_dependencies.sh` inside the graph build, so the producer/consumer
boundary is acyclic.

`public-surface` closes the public-fact producer boundary. Extend the existing
producer-only `tool_catalog.py` with exact symbols
`PublicSurfaceRow`, `PublicSurfaceReport`, and `extract_public_surface(root)`;
the existing `Finding`, `CatalogRow`, `CatalogReport`, `load_catalog`, and
`validate_catalog` remain the catalog validation/reuse boundary. The extractor
has five fixed inputs and no directory-wide heuristic: top-level Rust dispatch
is read from `rust/agent-canon/src/main.rs`, graph operation dispatch is read
from `rust/agent-canon/src/graph.rs`, CLI names and operation descriptions are
read from the `graph build|status|query|context` entries in
`agents/canonical/CLI_ENTRYPOINTS.md`, catalog tool rows come from
`tools/catalog.yaml`, and skill rows come from `agents/skills/catalog.yaml`.

The Rust extractor is a bounded token parser, not a regex or Rust compiler. It
lexes UTF-8 identifiers, normal string literals, punctuation, and balanced
delimiters; skips line/block comments while retaining one-based start/end
line/column spans; and rejects an unterminated comment/string or unbalanced
delimiter. Inside `fn main`, the accepted top-level command grammar is exactly:

```text
if args.len() >= 2 && args[1] == <command-string> {
    std::process::exit(<module-ident>::<function-ident>(&args[2..]));
}
```

The graph route must be the unique specialization
`<command-string>="graph"`, `<module-ident>=graph`, and
`<function-ident>=run`, accompanied by one `mod graph;` declaration. The
current `version`/`--version` branch is classified separately and every other
current manual dispatch arm is accepted by the same token grammar, including
the existing `run_check` function name. In `graph.rs`, `pub(crate) fn
run(args:&[String])->i32` must use the current structured-analysis style:
`let Some(command)=args.first() else {...};` followed by
`match command.as_str()` with exactly one literal arm each for `build`,
`status`, `query`, and `context`; each arm calls its corresponding
`run_<operation>(&args[1..])`. Help aliases and the wildcard error arm emit no
public operation row. A comment, usage string, macro body, enum-derived or
Clap-derived dispatch, duplicate literal arm, wrong argument index/slice,
or semantically similar alternate dispatch shape emits no row and yields a
`public_surface.rust_dispatch_invalid` or
`public_surface.rust_dispatch_ambiguous` producer diagnostic. Rust syntax and
compilation remain authoritative to `cargo check`; this parser owns only the
public-dispatch projection.

For each `graph <operation>` row, the matching `graph.rs` literal arm is the
primary span, while the unique `main.rs` graph arm and matching CLI document
entry are sorted secondary spans. Missing any of the four operation arms,
missing `mod graph;`, or retaining a public `dependency-manifest normalize`
arm is a producer failure before graph publication.
Each emitted row carries the exact input path and line span, a stable
`surface_id`, `kind=cli|tool|skill`, `selector`, and `authority=public-surface`.
Derive `surface_id` exactly as `kind + ":" + canonical_selector`, where
`canonical_selector` is the case-preserving selector with ASCII whitespace runs
collapsed, path separators normalized to `/`, and catalog aliases resolved to
their declared canonical key. The Rust dispatch is the primary span for `kind=cli`;
catalog YAML is the primary span for `kind=tool|skill`; matching documentation
or catalog corroboration is sorted into `secondary_spans`. Same-kind rows with
the same `surface_id` merge only when selector and public operation agree; their
spans are sorted and deduplicated. Any conflicting selector, kind, or authority
for one ID yields `Ambiguous(public_surface.conflict)` and no `R` row; a
different kind has a different ID by construction. This is the deterministic
collision policy and is covered by the reproducibility oracle.
The JSON artifact is the `CatalogBundle` envelope: `catalog` is the existing
`CatalogReport`, while `public` is the `PublicSurfaceReport` with its sorted
`rows` and `producer_version`; graph build rejects a missing required row,
duplicate `surface_id`, or row lacking a span. `tool_catalog.py` keeps its
existing catalog-report callers on `catalog` and adds no decoder for an older
or alternate public shape.
This is the sole parser for these public semantics; graph materialization validates and
joins the report but never scans `main.rs` or Markdown itself.

The concrete relation-kind matrix fixes every worker join:

| RelationKind | Producer and exact output | Failure / `X_R`/`Unresolved`/`Ambiguous` rule | Side-Effect Map | Trace row | Validation oracle |
| --- | --- | --- | --- | --- | --- |
| `dependency` | `source-snapshot`; `ManifestParser::parse` declarations | malformed producer artifact is `invalid/build-failed`; unsupported target is `X_R` with reason | `SEM-01`, `SEM-04` | `SEM-01`, `SEM-04` | 2, 9, 14 |
| `owner` | `responsibility-scope`; `responsibility_scope.py --format json` | missing owner is `Unresolved`; excluded surface is `X_R` | `SEM-04`, `SEM-05` | `SEM-01`, `SEM-04` | 3, 9, 20 |
| `scope` | `responsibility-scope`; `ScopeReport` JSON | conflicting scope rules are `Ambiguous`; explicit boundary is `X_R` | `SEM-04`, `SEM-05` | `SEM-01`, `SEM-04` | 3, 9, 20 |
| `import` | `code-dependencies`; TSV rows with exact `kind=import` | empty target is `Unresolved` with `scanner.target_unresolved`; malformed artifact is `invalid/build-failed`; policy findings from `import-responsibility` never duplicate this edge family | `SEM-01`, `SEM-04` | `SEM-01`, `SEM-04` | 4, 9, 20 |
| `include` | `code-dependencies`; C-family `kind=include` and shell `kind=source` normalize to `RelationKind=include` with language retained | empty target is `Unresolved`; unsupported suffix is `X_R`; malformed artifact is `invalid/build-failed` | `SEM-01`, `SEM-04` | `SEM-01`, `SEM-04` | 4, 9, 20 |
| `symbol` | `code-dependencies`; TSV `kind=from-import-symbol` maps to symbol facts | empty target is `Unresolved`; duplicate/ambiguous target joins are `Ambiguous`; no Python symbol edge is taken from `ImportRecord` | `SEM-04`, `SEM-05` | `SEM-01`, `SEM-04` | 4, 9, 20, 21 |
| `call` | no current producer; `code-dependencies` capability metadata records `call=unsupported` as an `X` diagnostic, not a TSV relation | every default `call` query returns the typed unsupported diagnostic and no `R` edge; a future call producer requires a new design review | `SEM-04`, `SEM-05` | `SEM-01`, `SEM-04` | 9, 20, 21 |
| `containment` | `structured-analysis`; document-inventory JSON and Graph DSL document/node rows | inventory join failure is `Unresolved`; generated output boundary is `X_R` | `SEM-03`, `SEM-05` | `SEM-03`, `SEM-05` | 3, 6, 20 |
| `document` | `structured-analysis`; document inventory findings | ambiguous document relation is `Ambiguous`; historical/generated document is `X_R` | `SEM-03`, `SEM-05` | `SEM-03`, `SEM-05` | 9, 20, 21 |
| `catalog` | `structure-catalog`; `tool_catalog.py --root <parent-root> --format json` | invalid catalog artifact is `invalid/build-failed`; excluded/generated catalog is `X_R` | `SEM-09` | `SEM-09` | 17, 20, 21 |
| `pin` | `source-snapshot`; structure mapping is secondary provenance only | missing/moved pin is `Unresolved`; non-parent submodule internals are `X_R` | `SEM-02`, `SEM-05` | `SEM-02`, `SEM-05` | 3, 19, 20, 21 |
| `view` | `structure-catalog`; root/view mapping from structure contract | duplicate logical mapping is `Ambiguous`; view duplicate is `X_R` after canonical identity selection | `SEM-02`, `SEM-05` | `SEM-02`, `SEM-05` | 3, 19, 20, 21 |
| `generated` | `structure-catalog`; source content/fingerprint is secondary provenance only | unclassified generated path is `Unresolved`; classified generated path is `X_R` | `SEM-01`, `SEM-05` | `SEM-01`, `SEM-05` | 3, 19, 20, 21 |
| `submodule` | `source-snapshot` Git submodule entry plus pin/view provenance | missing pin is `Unresolved`; submodule internals are `X_R` | `SEM-02`, `SEM-05` | `SEM-02`, `SEM-05` | 3, 19, 20, 21 |
| `public` | `public-surface`; `tool_catalog.py::extract_public_surface` token-parses the fixed `main.rs`/`graph.rs` manual dispatch and validates `CLI_ENTRYPOINTS.md`, `tools/catalog.yaml`, and `agents/skills/catalog.yaml` | missing public route is `Uncovered`; private/deferred or non-grammar route is `X_R` | `SEM-09` | `SEM-09` | 15, 17, 20, 21, 30 |

The optional semantic-index DB is not part of `input_fingerprint` or graph
completeness: its advisory cache can be rebuilt independently. `graph context`
reports its resolved cache path, cache content hash, and `available|missing|stale`
state beside the exact graph evidence. A missing semantic index never promotes
text similarity into `R` and never makes a graph `fresh` claim false.

### Relation and reverse-edge rules

Each explicit edge stores `producer`, `authority`, `source_path`, `source_span`
when available, `owner`, `relation_kind`, and `evidence_ref` in `payload_json`.
Manifest declarations, code/import facts, responsibility facts, and structured
analysis findings remain distinguishable layer/kind records. A derived
containment or reverse lookup is marked `inferred` and is not an explicit
producer fact.

Reverse-edge closure means index closure, not synthetic source declarations:
for every edge `(a, b, k, e)` in `G`, `query outgoing a` and `query incoming b`
return the same edge identity, kind, and evidence; `query both` is the union
of those two projections. A missing producer-declared reverse line is a
diagnostic in `Unresolved` or `Ambiguous` only when the selected profile
requires that declaration.

## Storage, source scope, and naming contract

The only generated graph file is
`<parent-root>/.agent-canon/knowledge-graph/graph.sqlite`. It is parent-owned,
untracked/generated, and created by `graph build`. AgentCanon never writes a
graph DB under `vendor/agent-canon`.

The candidate graph reuses Graph DSL tables `documents`, `nodes`, `edges`,
`diagnostics`, and `metadata`. If projection membership needs a dedicated
table, use the existing Graph DSL projection representation; do not create a
parallel normalized-record schema. `payload_json` carries producer identity,
source locators, owner evidence, completeness-set labels, and query witness
data. The database records schema version, root, snapshot identity, producer
artifact hashes, tool versions, `profile`, `source_snapshot_profile`, and
`input_fingerprint` in metadata.

`input_fingerprint` is a deterministic digest of the canonical source manifest,
producer artifact identities/content hashes, the canonical profile tuple
`graph_profile=default\0source_snapshot_profile=parent`, schema version, and
tool versions. The profile tuple is included exactly once after the sorted
producer identities; neither the omitted-versus-explicit CLI spelling nor a
candidate path enters the digest. It is a freshness key, not an externally
exposed byte-level transport schema. Graph IDs are stable within the snapshot
and derived from source locator plus layer/kind and producer-local identity;
timestamps and enumeration order are not identity inputs.

### Identifier and naming plan

Names follow local Rust `*Args`, `*Result`, `run`, and Graph DSL table
precedent. No new config key is introduced and no public API is added outside
the four CLI subcommands.

| Kind | Fixed identifier | Role |
| --- | --- | --- |
| New Rust file | `rust/agent-canon/src/graph.rs` | Single graph controller, store adapter, CLI parser, query/context projection. |
| New Python consumer class | `GraphClaimConsumer` in `tools/agent_tools/check_design_doc_claims.py` | `check_document(claim_path,claims)` verifies `GraphIntegrationRecord` from `GraphClient.status()` before calling canonical `context`/`query`; it owns no parser, schema, filesystem, or claim-fact store. |
| New module | `graph` in `rust/agent-canon/src/main.rs` | Public dispatch owner for `agent-canon graph ...`. |
| New args | `GraphBuildArgs`, `GraphStatusArgs`, `GraphQueryArgs`, `GraphContextArgs` | Explicit operation inputs; no hidden global config. |
| New records | `GraphSourceScope`, `GraphFact`, `DependencyFactDetail`, `GraphProjection`, `GraphNode`, `GraphQueryFact`, `GraphQueryResult`, `GraphDiagnostic`, `GraphIntegrationRecord`, `DurableGraphState`, `GraphStatusCode`, `GraphStatusResponse`, `GraphBuildResponse`, `GraphContextItem`, `GraphContextEvidence`, `GraphContextResult`, `CandidateHandle`, `GraphCandidateCleanup` | One-unit records over Graph DSL rows and producer evidence; `GraphNode` makes zero-hop query closure explicit, `DependencyFactDetail` preserves manifest direction/kind/reason for canonical consumers, `GraphIntegrationRecord` is the verified status-to-consumer gate, and `GraphQueryResult` is the exact query-to-JSON projection. `GraphStatusCode` is the public status union, `GraphStatusResponse`/`GraphBuildResponse` are the operation envelopes, `DurableGraphState` is the persisted DB-state subset, `CandidateHandle` is `pub(crate) struct CandidateHandle {dir:PathBuf,db:PathBuf}` returned only by candidate writing, and `GraphCandidateCleanup` is the explicit candidate-directory owner. |
| New external path type | `CachePath` | Semantic-index cache paths remain absolute/external or stable `cache:` identifiers; they are never represented as parent-relative `RepoPath` values. |
| New errors | `GraphError` | Typed command/stage failure without fallback route. |
| New functions | `run`, `snapshot_profile_for_graph`, `build_graph`, `read_graph_status`, `query_graph`, `context_graph`, `open_graph_store`, `materialize_graph_store`, `validate_graph_store`, `publish_graph`, `write_graph_candidate`, `validate_graph_connection`, `GraphCandidateCleanup::new`, `GraphCandidateCleanup::cleanup` | Exact controller boundaries; `run` uses the manual four-arm dispatch grammar above, `snapshot_profile_for_graph("default")` returns only `"parent"`, and `materialize_graph_store(&Connection, &GraphSourceScope, &[GraphFact], &[GraphProjection], &[GraphDiagnostic], &[ProducerArtifact], &GraphIntegrationRecord, &str) -> Result<(), GraphError>` is the sole graph.rs insertion adapter and calls existing `structured_analysis::initialize_graph_schema`; `GraphCandidateCleanup::new(dir:PathBuf)` and `cleanup(&self)` own candidate-directory deletion; names intentionally mirror existing Rust command modules. |
| New internal enum | `GraphBuildFailurePoint::{None, Producer, Validation, Write, Sync, Rename, DirectorySync}` | Explicit failure seams for candidate write, candidate file sync, validation, old-or-new publication, and directory durability; `Write` and `Sync` mirror `AtomicFailurePoint::{Write, Sync}` and are not public flags or transport schema. |
| Adapter signatures | `dependency_manifest::SnapshotRequest` is the existing crate-owned record `{root:PathBuf,profile:String,output_jsonl:PathBuf}`; `capture_snapshot(&SnapshotRequest) -> Result<ManifestSnapshot, ManifestError>` remains its producer boundary; existing `write_snapshot_jsonl(&ManifestSnapshot,&mut impl Write)` becomes `pub(crate)`; and new `snapshot_profile(&ManifestSnapshot) -> &str` exposes only `SnapshotHeader.profile` for join validation. For public graph profile `default`, graph constructs `SnapshotRequest {root:<resolved-parent-root>,profile:"parent".into(),output_jsonl:<candidate>/producer-artifacts/source-snapshot/source-snapshot.jsonl}`; it captures, writes, hashes, and validates that artifact before materialization. `structured_analysis::initialize_graph_schema(&Connection) -> rusqlite::Result<()>` becomes `pub(crate)`; new `structured_analysis::validate_graph_connection(&Connection) -> Result<(), String>`; new `semantic_index::graph_context_evidence(root:&Path,db:&Path,query:&str,provider:&str,model:&str,dim:usize,embedding_url:Option<&str>,max_cells:usize,max_cell_chars:usize,max_total_chars:usize,graph_fingerprint:Hex64) -> Result<Vec<GraphContextEvidence>, String>` converts every bounded private `ContextCell` to a crate-visible graph record; graph uses `DEFAULT_PROVIDER="deterministic-dense-v1"`, `DEFAULT_MODEL="hash-token-char-v1"`, `DEFAULT_DIM=128`, `DEFAULT_CONTEXT_CELLS=12`, `DEFAULT_CONTEXT_CELL_CHARS=900`, `DEFAULT_CONTEXT_TOTAL_CHARS=6000`, and the existing default embedding URL, with `query=token.unwrap_or(claim_path)` | Exact visibility and argument boundary; no module reaches another module's private CLI parser or exports `ContextCell` itself. |
| New Python adapter | `tools/agent_tools/graph_client.py`: `GraphClient`, `GraphClientError`, `GraphResponse`, `GraphDependencyFact`, `GraphClient.invoke`, `GraphClient.status`, `GraphClient.context`, `GraphClient.query`, `GraphResponse.dependency_facts` | One consumer-only subprocess/JSON adapter reused by `check_design_doc_claims.py`, `check_dependency_headers.py`, `search.py`, `search_index.py`, `vector_search.py`, `tool_drift.py`, and graph render/check wrappers. It invokes exactly `[<parent-root>/vendor/agent-canon/tools/bin/agent-canon, graph, <command>, --root, <parent-root>, --profile, default, --format, json, ...]` with `cwd=<parent-root>`, captures stdout/stderr, parses the fixed schema, preserves valid nonzero `exit_code`, and raises only for missing executable, process launch failure, invalid JSON, wrong schema, unsupported schema version, or a malformed endpoint/detail join. `GraphResponse.dependency_facts` selects only `kind=dependency,inferred=false`, joins endpoint IDs through `nodes`, rejects an explicit fact with null/invalid `DependencyFactDetail`, ignores inferred reverse projections for declaration-policy consumers, and emits sorted typed rows. Consumers convert errors to typed unavailable findings; none falls back to filesystem or header parsing. |
| CLI path | `agent-canon graph build|status|query|context` | Generic public surface; `--root` selects parent root; DB path is fixed. |
| CLI flags | `--root`, `--format`, `--path`, `--all`, `--token`, `--relation`, `--direction`, `--depth`, `--profile` | Only flags needed for the four operations; all are documented and validated. |
| Fixed output path | `.agent-canon/knowledge-graph/graph.sqlite` | Parent-owned generated state; not a config key. |
| Consumer result names | `GraphQueryResult`, `GraphContextItem`, `GraphClaimConsumer`, `ClaimTokenClass` | `GraphClaimConsumer` in `tools/agent_tools/check_design_doc_claims.py` is the only surviving checker identity; it requires verified `GraphIntegrationRecord` and uses only canonical status/query/context results. `ClaimTokenClass` remains input classification, never claim-fact authority. |
| Removed names/routes | `dependency-manifest normalize`, `NormalizedRecordSetV1`, `RelationRegistryArtifactV1`, `RelationNormalizer`, `read_normalized_record_set`, `bind_r2_scope.py`, `r2_scope_manifest.v1`, `r2_review_closeout.v1` | No compatibility alias or hidden alternate route. |

The new Rust records and arguments have these exact schemas; no field or
variant is left for the worker to invent:

- `GraphSourceScope = {root:PathBuf, profile:String, source_snapshot_profile:String, snapshot_head:String, candidate_paths:Vec<RepoPath>, excluded_paths:Vec<RepoPath>, input_fingerprint:Hex64}`; its only version-one pair is `profile="default"`, `source_snapshot_profile="parent"`.
- `GraphFact = {id:String, layer:String, kind:RelationKind, from:String, to:String|null, payload_json:String, producer:String, source_path:RepoPath|null, source_span:SourceSpan|null, evidence_ref:String, authority:String, inferred:bool, dependency_detail:DependencyFactDetail|null}`. `dependency_detail` is required for explicit `dependency` facts and null for every other relation family and every derived reverse projection, whose source fact remains reachable by ID.
- `GraphProjection = {id:String, projection:String, member_id:String, source_fact_ids:Vec<String>, payload_json:String, evidence_ref:String}`; it is derived only from `G`.
- `GraphDiagnostic` uses the exact declaration above; its canonical JSON contains `id`, `set`, `code`, `severity`, `relation`, `path`, `target`, `source_span`, `reason`, `producer`, `evidence_ref`, and `suggested_action_json`, with enum values `unresolved|ambiguous|uncovered|excluded` and `info|warn|blocker`. `X_R` maps to `set=Excluded` with a relation, target, producer, rule code, and `Info`; `O\\D` and `D\\O` map to `set=Uncovered` with source/target/span and `Warn` unless an explicit producer exclusion maps them to `Excluded`; unresolved and ambiguous records use their corresponding set and retain the candidate identity/span. `GraphError` handles malformed producer output and operation failures, so no `Error` diagnostic severity exists. The stable `id` is `set:code:<relation-or-empty>:<path-or-empty>:<target-or-empty>`; `suggested_action_json` is canonical sorted JSON with `action`, `owner`, and `retryable`. These mappings are the complete diagnostic payload used by materialization and the three public projections.
- `GraphError = {Usage(String), Producer{producer:String,reason:String}, Validation{stage:String,reason:String}, CandidateWrite{reason:String}, CandidateSync{reason:String}, Rename{reason:String}, DirectorySync{reason:String}, Unavailable{reason:String}}`.
- `GraphBuildArgs = {root:PathBuf, profile:String, format:OutputFormat}`; `GraphStatusArgs` has the same fields; `GraphQueryArgs = {root:PathBuf, profile:String, format:OutputFormat, path:Option<RepoPath>, all:bool, relation:RelationSelector, direction:GraphDirection, depth:u8}`; `GraphContextArgs = {root:PathBuf, profile:String, format:OutputFormat, path:RepoPath, token:Option<String>}`.
- `OutputFormat = {Text, Json}`; `GraphDirection = {Outgoing, Incoming, Both}`. `GraphStatusCode = {Fresh, Missing, Stale, Incomplete, Invalid, SchemaMismatch, Unavailable, BuildFailed, PublicationFailed}`; `graph::run` manually dispatches the four operation literals to the corresponding argument parser, `GraphStatusResponse` is the status envelope, and `GraphQueryResult` is the exact query response object already mapped below.
- `GraphBuildFailurePoint` is injected only through `build_graph_with_failure(args:&GraphBuildArgs, point:GraphBuildFailurePoint) -> Result<GraphBuildResponse,GraphError>` in source tests; production `build_graph(args)` supplies `None`. The same point is passed to `write_graph_candidate(..., point)` and `publish_graph(..., point)`: `Producer`/`Validation` fail before candidate publication, `Write`/`Sync` fail during candidate file creation, `Rename` fails before replacing the DB, and `DirectorySync` fails after rename. There is no CLI flag or environment switch for this seam.

`GraphFact` is the single new fact record. It is not a second semantic model:
its `layer`, `kind`, and `payload_json` map directly to Graph DSL and producer
records. `GraphProjection` is a view record and cannot be used as an input
fact. `GraphQueryResult` maps `facts`, `unresolved`, `ambiguous`,
`graph_fingerprint`, `reason`, and `exit_code` to the query JSON schema.
`GraphContextItem` is a return projection, not persisted source truth.
`GraphContextEvidence` is the crate-visible conversion record
`{path:PathBuf,source_span:Option<SourceSpan>,owner:Option<String>,content_sha256:Option<Hex64>,cache_state:SemanticIndexState,rank:u64,score:f64,kind:String,bucket:String,excerpt:String}`;
`SemanticIndexState = {Available, Missing, Stale}`. The adapter maps
`ContextCell.path`, `line_start`, `line_end`, `rank`, `score`, `node_kind`, `responsibility_bucket`,
and `excerpt` directly; it does not derive a hash from excerpt text. For an
existing `ContextCell`, `line_start` and `line_end` are one-based inclusive
line numbers, exactly as the current `line_range_text` helper applies them.
The adapter rejects `line_start < 1`, `line_end < line_start`, or
`line_end > text.lines().count()` with `semantic-index.line_range_invalid`.
For an accepted range, the graph reads complete source lines and maps the
first line to `start_column=1` and the last line to its exclusive UTF-8 byte
end; a missing optional span is never encoded as a fabricated zero-coordinate
span. The graph reads the authoritative source bytes and maps
`line_start` to `start_column=1` and `line_end` to
`end_column=<UTF-8 byte length of that complete line>+1`; it preserves the
semantic-index line range and uses the exact source bytes for the Graph DSL
character-offset conversion above. A missing path, zero/descending line
range, line beyond EOF, or cell/source hash mismatch is a typed stale-path
diagnostic with code `semantic-index.path_missing`,
`semantic-index.line_range_invalid`, or `semantic-index.hash_mismatch` as
applicable, never a guessed span. Their exact context-only classifications are
`semantic-index.path_missing=Unresolved/Warn`,
`semantic-index.line_range_invalid=Unresolved/Warn`,
`semantic-index.hash_mismatch=Uncovered/Warn`,
`semantic-index.db_missing=Unresolved/Warn`,
`semantic-index.graph_stale=Uncovered/Warn`,
`semantic-index.stale_path=Uncovered/Warn`, and
`semantic-index.embedding_missing=Uncovered/Warn`; they are returned in
`GraphContextResult.context_diagnostics` and do not change persisted graph
completeness. The graph joins the cell path and line range
to the source-snapshot row to obtain the exact `SourceSpan`, owner, and source
content hash. It computes `Missing` when the resolved `default_db_path` does
not exist (`semantic-index.db_missing`), and `Stale` when the graph itself is
not fresh (`semantic-index.graph_stale`), any selected cell's
`files.content_hash` differs from the graph source row
(`semantic-index.hash_mismatch`), the semantic index reports stale paths
(`semantic-index.stale_path`), or the requested provider/model/dim embedding
rows do not exist (`semantic-index.embedding_missing`). The current semantic-index
schema stores per-file hashes but no graph/source fingerprint, so the adapter
does not claim a nonexistent fingerprint comparison; graph freshness is
checked by graph preflight and file freshness by the explicit hash join. The
current schema does not store query bounds, so bounds are applied by the
existing context-pack call and are not falsely treated as stored metadata.
`semantic_index::graph_context_evidence` constructs a `Vec<GraphContextEvidence>`
with one record per bounded `ContextCell` from private rows without exposing
the semantic-index type or copying its embedding data into the graph. It passes
the requested `provider`, `model`, `dim`, and optional `embedding_url` through
the existing `ContextPackArgs` path; the graph does not invent an embedding
provider or silently widen any bound.
For each selected cell, `context_graph` emits one `GraphContextItem` with
`source_store=semantic-index`, `value=excerpt`, `rank`, `score`, `bucket`,
`cache_state`, and `evidence_ref=semantic-index:<repo-key>/<path>:<start_line>-<end_line>:<rank>`;
the graph-joined `source_path`, `source_span`, owner, producer, and content hash
are carried in the same item/result. Empty excerpts remain items with an empty
value; they are not dropped or treated as source truth.

## Public CLI contract

The public-surface effects are part of this contract: operators and skills use
only `agent-canon graph build|status|query|context`; the parent README/CLI
entrypoints and generated/root views name the parent-owned DB; dependency,
search, render, drift, prose, and `check_design_doc_claims.py` outputs cite
graph producer/source evidence; workflow prompts and catalogs remove MCP/R2/
binder/normalized routes; and validation labels are `fresh`, `stale`,
`incomplete`, `missing`, `invalid`, `schema-mismatch`, `unavailable`,
`build-failed`, or `publication-failed`. The detailed Side-Effect Map below
joins each reader-facing surface to its owner, clause, and check; it does not
introduce another public route.

All operations accept `--root <parent-root>` and default to the current parent
repository. They use the fixed DB path. `--format json` is the machine-readable
form; text output is for operators. `status` never rebuilds or writes the DB;
it may invoke required producers read-only to recompute the current fingerprint
and report freshness.

| Command | Input | Result |
| --- | --- | --- |
| `graph build` | Parent root and optional profile | Captures `S`, invokes selected producers, materializes a candidate, validates scope/relations/Graph DSL, and atomically publishes the DB. |
| `graph status` | Parent root and optional `default` profile | Returns `GraphStatusResponse` with `GraphStatusCode`: durable `missing`, `fresh`, `stale`, `incomplete`, `invalid`, `schema-mismatch`, or `unavailable`, or read-only producer-probe `build-failed` with its reason. It never reads a transient build result or writes the DB. |
| `graph query` | Parent root, exactly one `--path` or `--all`, relation selector, direction, depth, and format | Returns graph facts/projections with stable IDs, layer/kind, exact source/owner evidence, and unresolved/ambiguous witnesses. `--all` is the bounded consumer scan and requires `--depth 0`; it returns every persisted fact matching `--relation` without a path traversal. |
| `graph context` | Parent root plus required `--path` and optional `--token` and profile | Returns exact owner, source span/path, dependency witnesses, producer, and graph status for each selected item. |

### CLI argument matrix, schemas, and exit codes

All four commands accept `--root PATH` (default `.`), `--profile default`
(default `default`; any other value is a usage error), and `--format text|json`
(default `text`). The fixed database path is derived from the resolved root;
there is no public `--db` flag. Flags not listed for a command are rejected.

| Command | Required flags | Optional flags and defaults | Mutual exclusions and path rules |
| --- | --- | --- | --- |
| `build` | none | `--root .`, `--profile default`, `--format text` | Rejects `--path`, `--all`, `--token`, `--relation`, `--direction`, and `--depth`. |
| `status` | none | `--root .`, `--profile default`, `--format text` | Rejects query/context selectors and never rebuilds. |
| `query` | exactly one `--path REPO_PATH` or `--all` | `--relation all`, `--direction both`, `--depth 1` for `--path` and `0` for `--all`, `--profile default`, `--format text` | `--path` is one repo-relative path; `--all` requires `--depth 0`; absolute paths, `..` escapes, repeated selectors, and `--token` are rejected. `--depth` is an integer `0..64`; `--direction` is `outgoing|incoming|both`; `--relation` is one registered layer/kind or `all`. |
| `context` | exactly one `--path REPO_PATH` | one optional `--token TOKEN`, `--profile default`, `--format text` | `--token` requires `--path` as its claim-file context. `--path` is repo-relative and cannot escape the root. A token beginning `./` or `../` resolves from the claim-file directory; another relative token is root-relative; absolute tokens are invalid. |

`graph query` uses deterministic breadth-first closure for `--path` queries. It
uses a deterministic relation scan for `--all --depth 0` queries. It resolves the
canonical seed node(s) for `--path`; `depth=0` returns those seed nodes in the
`nodes` projection and no edges, so the seed is explicitly self-included.
For each depth `n > 0`, it traverses only edges matching `--relation` from the
current frontier, using outgoing, incoming, or both indexes according to
`--direction`; an edge is included once under its stable ID and a node is
visited once under its logical identity. Cycles and self-loops therefore
terminate and do not duplicate facts. `all` means every persisted
`RelationKind`, not inferred kinds. Results are ordered by minimum BFS distance
then stable ID, with ties in both-direction traversal resolved by the stored
edge ID; depth `1` is the default and `64` is the maximum. A missing seed is
`unresolved`; multiple canonical identities for the path are `ambiguous`.
`context` uses the same path normalization, then matches a non-path evidence
token against exact `evidence_ref` or exact `producer:key` selectors; zero
matches are unresolved and multiple matches are ambiguous. It never uses text
similarity to create a relation.

The JSON response schemas are fixed logical records, not byte-level transport
envelopes. Type labels such as `"u64"` and `"bool"` below describe JSON
types; they are not literal string values. `DurableGraphState` is the persisted
DB-state set `fresh|missing|stale|incomplete|invalid|schema-mismatch|unavailable`.
Public `GraphStatusCode` is the operation-status union
`fresh|missing|stale|incomplete|invalid|schema-mismatch|unavailable|build-failed|publication-failed`.
`build-failed` is also a read/query status when a required producer probe fails;
it carries the producer, failure stage, stderr summary, and reason without
writing a failure-state file. `publication-failed` is build-only because no
publication was attempted by read/query. Neither transient value is persisted
as a durable DB state.
Every operation response shares the status subset
`{status:GraphStatusCode,profile,root,db_path,graph_fingerprint,reason,stderr_summary,exit_code,unresolved_count,ambiguous_count,uncovered_count,excluded_count,unresolved,ambiguous,uncovered,excluded}`.
`status` adds integration/probe fields, `build` adds graph-state/publication/
durability fields, `query` adds nodes/facts, and `context` adds claim/evidence
fields; they are separate canonical response records, not one interchangeable
envelope. On a non-`fresh` status query/context returns empty facts/witness
projections, the reason, diagnostic sets, and nonzero exit code; it never
returns stale evidence.
The response records used by the schemas are defined before those schemas:
`RelationKind` is the closed enum
`dependency|owner|scope|import|include|symbol|call|containment|document|catalog|pin|view|generated|submodule|public`;
`RelationSelector` is `all|RelationKind`; `GraphNode` is
`{id:string,path:RepoPath|null,selector:string,layer:string,kind:string,owner:string|null,source_path:RepoPath|null,source_span:SourceSpan|null,distance:u8}`;
`ProducerArtifact` is
`{producer_id:string,version:string,command:string,root:RepoPath,content_sha256:Hex64,relation_families:[RelationKind],artifact_ref:string}`;
`GraphIntegrationRecord` is
`{schema:string,root:RepoPath,db_path:RepoPath,schema_version:string,profile:string,source_snapshot_profile:string,snapshot_head:string,input_fingerprint:Hex64,graph_fingerprint:Hex64,producer_artifacts:[ProducerArtifact],verified:bool,verification_code:string}`;
and `DependencyWitness` is
`{edge_id:string,relation:RelationKind,from:RepoPath,to:RepoPath,owner:string|null,source_path:RepoPath,source_span:SourceSpan|null,producer:string,evidence_ref:string,authority:string}`.
`GraphIntegrationRecord` is persisted in Graph DSL metadata as canonical JSON;
`verified=true` requires the DB schema, graph fingerprint, producer artifacts,
freshness probe, completeness state, and exact profile pair
`profile="default"`/`source_snapshot_profile="parent"` to match. A non-fresh,
invalid, schema-mismatched, or profile-mismatched graph returns
`integration_record=null`.
`status` returns
`{"schema":"agent-canon.graph.status.v1","command":"status","status":"GraphStatusCode","profile":"default","root":"RepoPath","db_path":"RepoPath","input_fingerprint":"Hex64|null","graph_fingerprint":"Hex64|null","integration_record":"GraphIntegrationRecord|null","unresolved_count":"u64","ambiguous_count":"u64","uncovered_count":"u64","excluded_count":"u64","unresolved":["GraphDiagnostic"],"ambiguous":["GraphDiagnostic"],"uncovered":["GraphDiagnostic"],"excluded":["GraphDiagnostic"],"reason":"string|null","stderr_summary":"string|null","producer_id":"string|null","failure_stage":"string|null","exit_code":"u8"}`.
`build` returns
`{"schema":"agent-canon.graph.build.v1","command":"build","status":"GraphStatusCode","graph_status":"DurableGraphState|null","profile":"default","root":"RepoPath","db_path":"RepoPath","input_fingerprint":"Hex64|null","graph_fingerprint":"Hex64|null","unresolved_count":"u64","ambiguous_count":"u64","uncovered_count":"u64","excluded_count":"u64","unresolved":["GraphDiagnostic"],"ambiguous":["GraphDiagnostic"],"uncovered":["GraphDiagnostic"],"excluded":["GraphDiagnostic"],"reason":"string|null","stderr_summary":"string|null","publication":"published|unchanged|not-published","durability":"durable|uncertain|not-durable","failure_stage":"string|null","exit_code":"u8","producer_artifacts":["ProducerArtifact"]}`. A successful complete build uses `status=fresh`, `graph_status=fresh`, `publication=published|unchanged`, `durability=durable`, and exit `0`. A successfully published but incomplete graph uses `status=incomplete`, `graph_status=incomplete`, `publication=published`, `durability=durable`, and exit `1`; its unresolved/ambiguous/uncovered sets remain queryable through status but no query/context evidence is authorized. Candidate capture, validation, candidate write/sync, or rename-syscall failure uses `build-failed` with `publication=not-published`, `durability=not-durable`, and exit `4`; only post-rename directory durability failure uses `publication-failed`, `publication=published`, `durability=uncertain`, and exit `5` because the renamed DB is already current. `graph_status` is null for the two operation-failure states. `producer_artifacts` contains producer ID, version, command, and content hash. `query` returns
`{"schema":"agent-canon.graph.query.v1","status":"GraphStatusCode","profile":"default","root":"RepoPath","db_path":"RepoPath","path":"RepoPath|null","all":"bool","relation":"RelationSelector","direction":"...","depth":"u8","graph_fingerprint":"Hex64|null","reason":"string|null","stderr_summary":"string|null","exit_code":"u8","unresolved_count":"u64","ambiguous_count":"u64","uncovered_count":"u64","excluded_count":"u64","nodes":["GraphNode"],"facts":[{"id":"string","layer":"string","kind":"RelationKind","from":"string","to":"string|null","owner":"string|null","source_path":"RepoPath|null","source_span":"SourceSpan|null","producer":"string","evidence_ref":"string","authority":"string","inferred":"bool","dependency_detail":"DependencyFactDetail|null"}],"unresolved":["GraphDiagnostic"],"ambiguous":["GraphDiagnostic"],"uncovered":["GraphDiagnostic"],"excluded":["GraphDiagnostic"]}`. A path query returns its normalized path and `all=false`; an all-query returns `path=null`, `all=true`, and requires `--depth 0`.
`context` returns
`{"schema":"agent-canon.graph.context.v1","status":"GraphStatusCode","profile":"default","root":"RepoPath","db_path":"RepoPath","claim_path":"RepoPath","token":"string|null","resolved_path":"RepoPath|null","source_span":"SourceSpan|null","owner":"string|null","dependency_witnesses":["DependencyWitness"],"items":["GraphContextItem"],"runtime_measurements":["RuntimeMeasurement"],"context_diagnostics":["GraphDiagnostic"],"producer":"string|null","semantic_index":"SemanticIndexState","semantic_index_path":"CachePath|null","semantic_index_content_sha256":"Hex64|null","graph_fingerprint":"Hex64|null","reason":"string|null","stderr_summary":"string|null","exit_code":"u8","unresolved_count":"u64","ambiguous_count":"u64","uncovered_count":"u64","excluded_count":"u64","unresolved":["GraphDiagnostic"],"ambiguous":["GraphDiagnostic"],"uncovered":["GraphDiagnostic"],"excluded":["GraphDiagnostic"]}`.
The canonical build-failure mapping is: producer, validation, candidate write,
candidate sync, or rename syscall failure -> `build-failed`,
`publication=not-published`, `durability=not-durable`, exit `4`; only a
post-rename parent-directory fsync failure -> `publication-failed`,
`publication=published`, `durability=uncertain`, exit `5`. The renamed DB is
current in the latter case; no rollback is attempted.
The published-incomplete build sentence above includes `Uncovered` as well as
`Unresolved` and `Ambiguous`: all three arrays remain available from `status`,
and query/context return them with empty facts/witnesses.
All nullable fields are explicit `null`. `nodes` and `facts` use the BFS
distance-then-stable-ID order defined above; `dependency_witnesses` and
`producer_artifacts` use stable edge/producer ID order; `unresolved`,
`ambiguous`, `uncovered`, and `excluded` use lexical `(code,path,reason)` order.
No response array relies on one universal sort rule.

`SourceSpan` is
`{path:RepoPath,start_line:u64,start_column:u64,end_line:u64,end_column:u64}`;
the response records above are the only nested public record definitions. `all`
is a query selector and never a persisted fact kind; `public` is produced only
by `public-surface` and is not inferred by graph queries. Nullable nested fields
are explicit `null`; response ordering is defined separately above for each
array family.
`ProducerArtifact.relation_families` is sorted by that exact closed-enum order;
`DependencyWitness` arrays use edge ID order; and every nested array in a
producer artifact or diagnostic payload is key/value canonicalized before its
content hash is recorded.
`PublicationState` is `published|unchanged|not-published`; `DurabilityState` is
`durable|uncertain|not-durable`. `build` may return
every `GraphStatusCode` value, with the two transient values only at their named
failure stage; `status`, `query`, and `context` return `GraphStatusCode` and use
`build-failed` for a required-producer failure before exposing evidence. A
valid nonzero response remains a parsed `GraphResponse`; its
`exit_code` is not converted into a transport exception.

Exit codes are fixed: `0` means a successful build/query/context or `fresh`
status; `1` means a valid non-fresh status (`missing`, `stale`, or
`incomplete`) or a query/context refusal caused by one of those states; `2`
means usage/selector/schema error; `3` means `invalid`, `schema-mismatch`, or
`unavailable` status; `4` means `build-failed` during candidate capture,
validation, or a status/query/context producer probe; `5` means
`publication-failed` during build. `build-failed` and `publication-failed` are
never persisted as a current graph status.
The machine-readable response is emitted before a nonzero state exit whenever
the command can produce one. `check_design_doc_claims` maps every non-`fresh`
state to its typed finding and never treats a nonzero graph exit as evidence.
If its caller reports a failed prerequisite build, it preserves
`build_status:build-failed` or `build_status:publication-failed` as the typed
finding and exits nonzero; it never retries or falls back to local parsing.

`graph context` is the only context expansion authority. It may include
semantic-index `ContextCell` excerpts, manifest edges, responsibility scope,
import/call evidence, and structured-analysis diagnostics, but each item must
name the source store and producer. It cannot invent a dependency because a
text match looks plausible.

## Freshness and atomic publication contract

`graph build` runs as one unit in this order: capture a stable snapshot; invoke
authoritative producers; compute `P`, `X`, and `U`; collect `D` and `R`; write
`.agent-canon/knowledge-graph/.candidate/<build-id>/graph.sqlite`; run Graph DSL
and relation validation; compute unresolved/ambiguous diagnostics and
`input_fingerprint`; commit and fsync the candidate; rename it to the fixed
parent path; fsync the parent directory; and remove the candidate directory.
A failed producer, validation, or pre-rename publication step leaves the
previous valid DB unchanged and removes the candidate directory.

`write_graph_candidate` reuses the existing `dependency_manifest.rs`
`write_atomic_with_failure`/`CandidateCleanup` pattern but owns only candidate
creation and candidate-file sync: its exact result is
`CandidateHandle={dir:PathBuf,db:PathBuf}`. It creates the unique candidate
directory, writes the SQLite DB, closes the connection, and syncs the candidate
file; it never renames or syncs the parent directory. `publish_graph` alone
owns the rename and parent-directory sync. Its internal `GraphBuildFailurePoint` seam covers
`Producer`, `Validation`, `Write`, `Sync`, `Rename`, and `DirectorySync`; the
`Write` and `Sync` cases are the graph-level injections corresponding to the
existing `AtomicFailurePoint::Write` and `AtomicFailurePoint::Sync` seams. The
seam is not a public CLI flag and exists only to exercise the source
mechanism's old-or-new invariant. `publish_graph` owns the rename and
directory sync, while `validate_graph_store` owns Graph DSL and relation
checks before publication. A failure at each seam has the exact prior-DB and
candidate-cleanup behavior stated here: every pre-rename failure removes the
candidate and leaves the prior DB readable; post-rename directory-sync
failure reports durability failure without rollback.
The new graph-owned `GraphCandidateCleanup` in `graph.rs` has the exact API
`GraphCandidateCleanup::new(dir:PathBuf) -> GraphCandidateCleanup` and
`cleanup(&self) -> Result<(),GraphError>`. It removes
`<dir>/graph.sqlite`, `<dir>/graph.sqlite-wal`, and `<dir>/graph.sqlite-shm`,
then the unique candidate directory; missing paths are ignored and any other
removal error is returned as `CandidateWrite`. `write_graph_candidate` owns
its pre-rename call, and `publish_graph` owns the post-publish call for
leftover temporary producer files. The existing dependency-manifest
`CandidateCleanup` remains only the current single-file atomic-writer pattern
read before this new graph-owned boundary; it is not silently repurposed.
The candidate layout is fixed as
`.agent-canon/knowledge-graph/.candidate/<build-id>/graph.sqlite` plus
`.agent-canon/knowledge-graph/.candidate/<build-id>/producer-artifacts/<producer-id>/`
and `scanner-paths.txt`. `GraphCandidateCleanup` owns every file and directory
under that one `<build-id>` directory, including all producer outputs; it
never removes `~/.cache/agent-canon`, `.agent-canon/log-archive`, the four
runtime-result directories, or any producer-owned archive. Before rename it
removes the complete candidate directory after materialization. After rename
it attempts the same cleanup; a failed attempt preserves the candidate for
diagnosis and reports its bounded logical directory reference in the typed
post-publish error.
`GraphBuildFailurePoint::Rename` is the rename syscall returning before the
fixed path changes and therefore follows `build-failed`; only
`GraphBuildFailurePoint::DirectorySync` occurs after the fixed path changes and
follows `publication-failed`. A `GraphCandidateCleanup::cleanup` error before
rename maps to `build-failed`, `publication=not-published`,
`durability=not-durable`, exit `4`, and leaves the prior DB current. A cleanup
error after rename maps to `publication-failed`, `publication=published`,
`durability=uncertain`, exit `5`; the new DB remains current, no rollback is
attempted, and the response carries `failure_stage="post-publish-cleanup"`
plus the typed reason. This is the same post-rename status contract as parent
directory fsync failure.

`status` first applies the same `default -> parent` adapter and probes the
required producers read-only using temporary outputs; this probe is not a build
and never publishes. It requires the captured `SnapshotHeader.profile`, graph
metadata `source_snapshot_profile`, and integration-record field all to equal
`parent`, while their public `profile` fields equal `default`; a mismatch is
`invalid` with `integration_record=null` before any facts are exposed. If a required probe fails,
`build-failed` is returned even when no DB exists, so a first-build failure is
visible. If probing succeeds, it then evaluates the DB in this exact order:
OS/runtime path-unavailable -> `unavailable`; absent DB -> `missing`; opened
DB failing Graph DSL -> `invalid`; unsupported schema marker ->
`schema-mismatch`; differing input fingerprint -> `stale`; nonempty
`Unresolved`, `Ambiguous`, or `Uncovered` -> `incomplete`; otherwise `fresh`.
The same producer-first rule applies to query/context preflight; neither
operation rebuilds or publishes. A published incomplete graph remains current,
but query/context return its diagnostics without facts.
`graph build` returns the same producer/publication error as a command failure,
does not persist a failure status, and leaves the prior DB unchanged until a
successful rename. No partial candidate is a readable public state.

Schema handling is replacement-only, never migration-in-place. The current
`schema_version` is the fixed `graph_storage_core.v1` value named by the
existing Graph DSL implementation. `status` reports `schema-mismatch` when the existing DB has
another version or cannot satisfy the v1 table/metadata contract. `build` does
not open that DB for mutation and does not attempt an in-place migration: it
constructs a fresh v1 candidate from the current snapshot and producers, runs
the complete v1 validator, and atomically replaces the old path only after
validation. If candidate construction fails, the mismatched DB is left intact
and the build response is `build-failed` with `publication=not-published`.
Canonical/view identity normalization is applied before this schema validation,
so a rebuilt v1 graph has one deterministic logical ID for every accepted source
regardless of aliases. A database that is a directory, unreadable, or not a
SQLite file is `unavailable`/`invalid` by the existing status precedence and is
also never modified by build.

Publication failure has one explicit boundary. Before `rename`, the candidate,
SQLite journal/WAL, and temporary producer artifacts are removed and the prior
DB remains current. After `rename` but before the parent-directory `fsync`, the
new candidate is already the only current path; the command returns
`publication-failed`, `publication=published`, `durability=uncertain`, and exit
`5` without attempting rollback. The next `status` validates that file and
returns `fresh`, `incomplete`, `stale`, or `invalid`; the client must treat the
old-or-new DB invariant as satisfied but the build operation as not durable.
This preserves the old-or-new reader invariant without a second failure-state
file.

## `check_design_doc_claims` decision

The implementation identity is **graph-owned consumer** at the existing path
`tools/agent_tools/check_design_doc_claims.py`. The current checker has a valid
semantic need that must be preserved: a token can be a resolvable path, a graph
evidence selector, or math/prose, and relative paths resolve from the claim
document rather than silently from repository root. This identity does not
preserve the old implementation. All ad-hoc manifest parsing, transport/schema
decoding, filesystem corpus walking, dependency closure, and local claim-fact
evaluation are deleted or replaced by the canonical graph operations below.

Retain only `ClaimTokenClass`, the claim-token cue classification needed to
distinguish path/evidence/math, `Claim`, `Finding`, `CheckResult`, `build_parser`,
output rendering, and the existing public command shape. These retained symbols
classify input and render graph results; they cannot establish claim truth or
dependency facts. Delete/replace `ManifestEdge`, `strip_manifest_line`,
`parse_manifest_edges`, `all_manifest_edges`, `dependency_closure`, local
`resolve_claim_token_path` evidence expansion, every ad-hoc schema/transport
decoder, and every direct filesystem corpus walk. Replace them with:

1. `graph status` to require a fresh graph or return the typed non-fresh status finding defined below.
2. `graph context --path <claim-file> --token <token>` for authoritative path resolution and exact graph evidence.
3. `graph query` for dependency closure and parent/downstream witnesses.
4. Existing token classification to decide whether a token requires path
   resolution, graph evidence, or both; it never decides the evidence result.

The exact consumer boundary is `GraphClaimConsumer(client: GraphClient)` with
`check_document(claim_path: str, claims: Sequence[Claim]) -> CheckResult`;
`Claim = {path:String,line:u64,text:String,tokens:tuple[String,...]}` is the
existing input record and is retained so every finding preserves its source
line and claim text context.
`check_document` first obtains `status`; it may call `context` or `query` only
when the response contains a verified `GraphIntegrationRecord` and
`status=fresh`. Without that record it returns the typed finding
`graph-integration-unverified` and cannot act on any token. Its only path and
evidence inputs are `resolved_path`, `source_span`, `owner`,
`dependency_witnesses`, `producer`, and `graph_fingerprint` from graph JSON.

The existing control-flow symbols map without a second fact route: retained
`selected_paths(root,args)` continues to implement `--changed` and explicit
multi-document selection; retained `extract_claims(path,text)` supplies the
input `Claim` records and claim count only; replaced
`check_one(root,path,edges,recursive_depth)` becomes
`GraphClaimConsumer.check_document`. `--recursive-depth` is passed as the
graph query `depth` (the existing nonnegative bound remains), and the consumer
calls `query(path=claim_path, all=false, relation="dependency",
direction="both", depth=recursive_depth)`. For every returned fact it joins
`GraphQueryFact.from`/`to` to the returned `GraphQueryResult.nodes` by stable
ID and accepts only the source-node `GraphNode.path` projection. Outgoing
endpoint paths become sorted `CheckResult.evidence_paths`; incoming endpoint
paths become sorted `CheckResult.parent_paths`; a missing endpoint row or a
non-source endpoint is the query's typed unresolved finding, never a path
parser or filesystem fallback. Duplicate edge IDs are collapsed by the graph
result. `check_parent_contradictions` consumes incoming facts and
`GraphContextItem` owner/source evidence, `check_claim_support` matches only
graph context items and the resolved path/span, and
`missing_dependency_target_findings` is replaced by the query's typed
unresolved/ambiguous diagnostics. `main(argv)` keeps the existing parser,
`--format`, result rendering, and exit rule, constructs one
`GraphClaimConsumer(GraphClient(root, executable))`, and checks every selected
document; it never constructs manifest edges or a filesystem evidence corpus.
For each `Claim`, a path token is supported only when `context` returns a
non-null `resolved_path` and `source_span`; an evidence token is supported only
when a returned `GraphContextItem` value/evidence reference or dependency
witness matches it; math/prose tokens are classified locally and are never
promoted. A missing match creates the existing
`Finding("claim-token-without-evidence",claim.path,claim.line,"token=<token>;reason=<graph-code>")`.
`CheckResult = {path,claims=len(claims),supported_claims,evidence_paths,
parent_paths,findings}`; `evidence_paths` and `parent_paths` are exactly the
sorted outgoing/incoming dependency endpoint paths obtained by the
`GraphQueryFact`-to-`GraphNode` ID join.
For contradiction handling, `check_document` calls `context(parent_path,None)`
for each incoming parent path returned by the bounded query; it compares the
claim's existing polarity classification with only those parent
`GraphContextItem.excerpt/value` strings and graph owner/source items. A claim
counts in `supported_claims` only when every checkable token has the required
path/evidence match and no contradiction finding is emitted; math/prose-only
claims retain the existing non-claim behavior. This is the complete replacement
for filesystem `evidence_texts` and `check_parent_contradictions` corpus reads.

All Python graph consumers use the same new `GraphClient` adapter. Its fixed
interfaces are `GraphClient(root: Path, executable: Path)`,
`invoke(command: str, arguments: Sequence[str]) -> GraphResponse`,
`status() -> GraphResponse`,
`context(claim_path: str, token: str | None) -> GraphResponse`, and
`query(path: str | None, all: bool, relation: str, direction: str, depth: int) -> GraphResponse`.
`path` is required exactly when `all=false`; `all=true` is the relation-scan
selector and requires `depth=0`.
The caller constructs `executable` as
`<parent-root>/vendor/agent-canon/tools/bin/agent-canon`; `invoke` runs with
`cwd=<parent-root>` and the exact argument prefix
`graph <command> --root <parent-root> --profile default --format json`, then appends the fixed
operation arguments. It parses only the public JSON schemas, preserves the
response `exit_code` and typed status, and raises `GraphClientError` for a
missing executable, process launch failure, or invalid JSON. The checker maps
that error to `graph-unavailable`; search and render consumers return their
existing error records with the same typed cause. No caller reads the DB,
scans headers, walks a corpus, or falls back to a second parser.

`check_design_doc_claims.py` classifies before invoking the adapter. A path
token calls `context(claim_path, token)` and uses only `resolved_path` and its
source span; an evidence token calls `context` and then `query` for its
dependency/owner witnesses; a math/prose token remains local classification
and does not become a graph fact. Relative token resolution stays in the graph
CLI: `./` and `../` are claim-file-relative, other relative tokens are
parent-root-relative, and absolute tokens are rejected. A non-fresh status or
`GraphClientError` becomes a typed finding, never evidence.

The CLI emits the flat command-specific JSON objects shown above; it does not
emit a second envelope. `GraphResponse` is the Python-only adapter record
`{schema: str, command: str, status: str, payload: Mapping[str, object],
exit_code: int}`, where `payload` is the parsed flat stdout object and
`GraphClient` exposes its fields by their top-level names. Stderr is attached
only to `GraphClientError`. `GraphClient.invoke` accepts exactly the
command allowlist `build|status|query|context`, requires the response schema
`agent-canon.graph.<command>.v1`, rejects an unsupported schema version, and
rejects duplicate or unknown flags before spawning. The adapter itself emits
only the command-specific argument sets in the CLI matrix, always supplies its
own root and `--format json`, and rejects `--db`, `--mcp`, arbitrary producer
names, and raw extra arguments. A process that starts and returns valid JSON
with exit `1..5` returns `GraphResponse`; only missing executable, process
launch failure, malformed JSON, wrong command/schema, or unsupported schema
version raises `GraphClientError`.

The consumer has an explicit status matrix: `fresh` permits token classification
and graph context; `missing`, `invalid`, `schema-mismatch`, `unavailable`,
`build-failed`, `stale`, and `incomplete` each emit a typed
`graph_status:<state>` finding,
include the status reason and unresolved/ambiguous counts when available, and
stop before claiming any token is supported. `missing`, `stale`, and
`incomplete` correspond to graph exit `1`; `invalid`, `schema-mismatch`, and
`unavailable` correspond to graph exit `3`; `build-failed` corresponds to graph
exit `4`. `incomplete` does not permit
partial support, and `stale` does not permit evidence from the old graph. The
checker exits with its existing nonzero finding result for all seven non-fresh
states; it never silently rebuilds or falls back to a local parser/filesystem
corpus.

The rejected alternate is deletion. It would remove the only existing
consumer-level distinction between resolvable paths and evidence tokens and
would lose the dirty branch's semantic intent. It is not selected.

## Preflight handoff order

The following gates are read and formed before the file-level plan is acted on;
the full normative tables remain below as durable detail, not as a reason to
backtrack during implementation:

1. Use the complete preflight index immediately below as the no-backtracking
   packet summary: it names the audit, user/search contracts,
   dependency-review artifacts, file-surface inventory, branch/dirty evidence,
   repository contracts, exact source symbols, and required review/validation
   commands. The expanded `Implementation Source Packet` later in this brief
   is mandatory before the writer edits, but it adds durable citations rather
   than a new decision or a competing route.
2. Read the `Current dirty-path disposition` and `Explicit deletion list`.
   The current modified paths are `documents/tools/check_design_doc_claims.md`,
   `rust/agent-canon/src/dependency_manifest.rs`,
   `tests/agent_tools/test_check_design_doc_claims.py`,
   `tests/agent_tools/test_dependency_manifest_tools.py`,
   `tools/agent_tools/bind_r2_scope.py`,
   `tools/agent_tools/check_design_doc_claims.py`, and
   `tools/agent_tools/dependency_manifest_records.py`; the three untracked
   dirty fixtures are `normalized_record_set.v1.jsonl`,
   `relation_registry.v1.json`, and `source_snapshot.v1.jsonl` under
   `tests/fixtures/dependency_manifest/`. Also inspect the four possible
   untracked runtime-result directories under
   `experiments/_template/result/readonly_agent_log_analysis_{dashboard,dashboard2,ensure,status}/`;
   preserve them if the parent checkout exposes them, and do not create them
   if this submodule checkout does not. Their semantic runtime evidence is
   consumed read-only by the dashboard producer. All graph-related semantic
   cases are ported before obsolete matrix/fixture deletion, and no dirty
   intent is reset.
3. Resolve each planned change through the `Design Side-Effect Map` and
   `Design-To-Implementation Trace`, including owner stage, review gate,
   validation, dependency-manifest edge, user-facing surface, and clause ID.
   These are one-unit integration joins, not independent work slices.
4. Only after those three gates pass does the one Luna writer execute the
   source-first plan below; split is allowed only for an actual write conflict
   or unresolved predecessor gate.

### Complete preflight index

The implementation stages used by the preflight and trace tables are defined
before their first use: `KG-SRC` is the source mechanism and durable-store
stage; `KG-CONSUME` is the graph CLI, consumer, documentation, skill, generated
view, and public-edge stage; and `KG-TEST-LAST` is the post-source deletion and
consumer-regression stage. The one Luna writer performs these stages in this
order inside one atomic responsibility unit; a split is allowed only for an
actual write conflict or unresolved predecessor gate.

This index is complete enough to execute the unit without backtracking; the
full tables below preserve the same rows as durable review detail.

| Preflight packet | Required contents before editing |
| --- | --- |
| `SP-1` request and branch | All `KG-*`, `BR-*`, and `SEARCH-*` clauses; `origin/main..HEAD` commits `ecacb84b`, `24c878b4`, `0a7cc98a`, `607c8e81`; current no-PR state; dirty semantic intent and user-owned preservation rule. |
| `SP-2` mathematical/current basis | `graph_architecture_audit.md`; `structured-analysis/graph-dsl.md`; `structured-analysis/database-design.md`; `dependency-manifest-design.md`; `dependency-header-analysis.md`; `semantic_index.md`; `search-coordination.md`; `responsibility-scope-management.md`; `SHARED_RUNTIME_SURFACES.md`; `shared-runtime-surfaces.toml`; `repo-structure-contract.toml`; `documents/README.md`, `tools/README.md`, `documents/tools/README.md`; `Cargo.toml`/`Cargo.lock`; `.codex/config.toml`. |
| `SP-3` source and symbols | Current symbols to read include `main.rs::main` and its repeated `if args.len() >= 2 && args[1] == "..."`/`run(&args[2..])` arms; `structured_analysis.rs::run` and its `args.first()`/literal-match dispatch; `dependency_manifest.rs::{ManifestParser,scan_manifest_lines,SnapshotRequest,SnapshotHeader,capture_snapshot,write_snapshot_jsonl,write_atomic_with_failure,AtomicFailurePoint,CandidateCleanup}`; `semantic_index.rs::{default_db_path,repo_cache_key,ContextCell}`; `tool_catalog.py::{CatalogReport,Finding,load_catalog,validate_catalog}`; `check_dependency_headers.py::{build_parser,changed_paths,should_check,has_dependency_manifest,has_dependency_header,strip_manifest_line,manifest_lines,contract_kind_findings,HEADER_SCAN_LINES}`; `search.py::{SearchCorpus,load_corpus,header_dependency_hits}` and its direct `vector_search.parse_dependency_edges` call; `vector_search.py::{DependencyEdge,parse_dependency_edges}`; `tool_drift.py::{ManifestEdge,has_dependency_manifest,strip_manifest_line,repo_relative,normalize_target,manifest_edges,HEADER_SCAN_LINES,MANIFEST_FIELD_COUNT,MANIFEST_REASON_MAX_SPLIT,check_catalog_entries,check_link,run_checks}` plus its `os` import; the runtime-dashboard symbols listed below; and every named producer JSON/TSV/event contract. Planned additions are `graph.rs::{run,run_build,run_status,run_query,run_context,snapshot_profile_for_graph}`, `graph_client.py::{GraphClient,GraphResponse,GraphDependencyFact}`, `tool_catalog.py::{PublicSurfaceRow,PublicSurfaceReport,extract_public_surface}`, `check_design_doc_claims.py::GraphClaimConsumer`, `RuntimePathResolution`, and `RuntimeMeasurement`; no command enum is planned. |
| `SP-4` dirty/deletion | Every current modified file, the three graph-related untracked fixtures, and the four possible parent runtime-result directories listed below; port graph-related semantic cases first, preserve runtime evidence bytes, then remove old normalized/binder/parser matrices, duplicate transport tests, and obsolete fixture files only after source checks pass. |
| `SP-5` binding scope | Exact dependency-header edit set includes `search.py` and `test_search.py` in addition to `graph.rs`, `main.rs`, `dependency_manifest.rs`, `structured_analysis.rs`, `semantic_index.rs`, `graph_client.py`, `check_design_doc_claims.py`, `check_dependency_headers.py`, `vector_search.py`, `search_index.py`, `tool_catalog.py`, `tool_drift.py`, `test_tool_drift.py`, `test_check_dependency_headers.py`, `test_tool_catalog.py`, the two small manual-dispatch fixtures, `prose_reasoning_graph.py`, dependency-check/render/review/scanner scripts, `import_responsibility.py`, `responsibility_scope.py`, graph docs, CLI/workflow docs, skills, catalogs, root/generated views, dependency headers, and the listed tests/fixtures; the four branch-inspection helpers remain read-only/out of scope. |
| `SP-6` review/validation | Fresh same-SHA detailed-design and document-flow approvals; `check_convention_compliance.py`; `agent-canon docs check`; `repo_structure_contract.py`; `responsibility_scope.py`; Rust build/check; graph CLI smoke/status/query/context; canonical runtime dashboard API generation plus token/hook/path source tests; source mechanism tests; dependency review; residual-parser/MCP/R2 scans; atomic/freshness/reverse-edge/reproducibility/runtime-evidence oracles. |

`SP-1` through `SP-6` are mandatory before editing. Historical review files are
optional archival context only; the predecessor integration record and archive
manifest are deferred successor inputs, and their absence blocks successor
authorization rather than changing this predecessor unit.

| Preflight side-effect ID | Owner stage | Review gate | Validation | Clause / reuse precedent |
| --- | --- | --- | --- | --- |
| `SEM-01` parser/full-file | `KG-SRC` | source | 1, 2, 14 | `KG-4`; `ManifestParser` |
| `SEM-02` parent DB | `KG-SRC` | source/parent | 3, 19 | `KG-2/3`; shared surfaces/Graph DSL |
| `SEM-03` Graph DSL | `KG-SRC` | storage | 5, 6, 20 | `KG-5`; `run_graph_contract` |
| `SEM-04` producer `D`/`R` | `KG-SRC` | dependency/source | 4, 9, 20 | `KG-4/8`; `ImportRecord`, `ScopeIndex`, `ContextCell` |
| `SEM-05` diagnostics | `KG-SRC` | mathematical | 6, 9, 21 | `KG-6`; `SourceUniverse` |
| `SEM-06` atomic/freshness | `KG-SRC` | lifecycle | 7, 8, 19, 31 | `KG-7`; `SnapshotRequest`, profile adapter, atomic writer/failure points |
| `SEM-07` claim consumer | `KG-CONSUME` | consumer/API | 7, 9, 20 | `BR-2`; `ClaimTokenClass`, `CheckResult` |
| `SEM-08` R2 deletion | `KG-TEST-LAST` | deletion/PR | 14, 16, 17 | `KG-3`, `BR-1/3`; dead-code evidence |
| `SEM-09` generic CLI/public producer | `KG-CONSUME` | API/flow | 9, 17, 20, 30, 31 | `KG-1/3`; manual `main.rs`, `structured_analysis::run`, catalog validator |
| `SEM-10` search/check/drift consumers | `KG-CONSUME` | consumer/dependency | 4, 5, 20, 27–29 | `KG-4/5/8`; `GraphDependencyFact`, `ContextCell`, retained consumer result records |
| `SEM-11` runtime evidence/dashboard | `KG-SRC` then `KG-CONSUME` | source/runtime + evidence | 22–26 | runtime-evidence delta; `AgentRuntimeDashboard`, `TokenFootprint`, `append_monitoring` |

| Preflight trace ID | Planned unit edit | Clause | Validation |
| --- | --- | --- | --- |
| `TR-1` | Add graph controller/Graph DSL adapter; fixed DB, lifecycle, diagnostics | `KG-1/2/5/6/7` | Rust checks; four graph commands |
| `TR-2` | Dispatch graph; make catalog/public extraction producer-only; delete public normalize route | `KG-1/3`, `BR-3` | CLI and catalog/public-surface checks |
| `TR-3` | Simplify manifest source mechanism; remove line cap and private transport | `KG-4/8` | full-file parser/provenance checks |
| `TR-4` | Add structured-analysis/semantic-index adapters; remove duplicate dependency extraction | `KG-5/8` | Graph DSL and context evidence checks |
| `TR-5` | Add graph client; convert dependency/search/render tools to consumers | `KG-4/5/8` | residual parser/fact-store and integration checks |
| `TR-6` | Replace `check_design_doc_claims.py` with verified graph consumer | `BR-2`, `KG-7` | path/evidence/math token cases |
| `TR-7` | Port dirty cases, delete R2/binder/decoder matrices and fixtures, update docs/skills/catalog/headers/views | `BR-1/3`, `KG-3/9` | source first; public regression/property only if missing |

Only after this complete index is read does the writer enter the detailed
file plan; the later Source Packet, Side-Effect Map, and Trace are exact
expanded forms of these same IDs, not new choices.

### Preflight scope snapshot

The scope decision needed by the file plan is complete here. Preserve these
modified paths and port their semantic intent before any deletion:
`documents/tools/check_design_doc_claims.md`,
`rust/agent-canon/src/dependency_manifest.rs`,
`tests/agent_tools/test_check_design_doc_claims.py`,
`tests/agent_tools/test_dependency_manifest_tools.py`,
`tools/agent_tools/bind_r2_scope.py`,
`tools/agent_tools/check_design_doc_claims.py`, and
`tools/agent_tools/dependency_manifest_records.py`. Preserve and port the
three untracked fixtures
`tests/fixtures/dependency_manifest/normalized_record_set.v1.jsonl`,
`tests/fixtures/dependency_manifest/relation_registry.v1.json`, and
`tests/fixtures/dependency_manifest/source_snapshot.v1.jsonl`; preserve without
editing the four possible parent runtime-result directories under
`experiments/_template/result/readonly_agent_log_analysis_{dashboard,dashboard2,ensure,status}/`
when exposed. The explicit deletion list is
`bind_r2_scope.py`, `dependency_manifest_records.py`, the three normalized/
relation-registry/source-snapshot fixtures, R2/binder/byte-schema matrices,
duplicate parser tests, and stale public normalize routes, only after the
single complete-file parser, graph store, runtime producer, CLI, and consumer
oracles pass. This snapshot is the authoritative preflight disposition; the
later dirty/deletion tables expand it and do not require a new scope decision.

## One-unit file-level change plan

Implementation topology is one full replaceable-unit pass by one Luna writer.
The writer owns the current dirty semantic intent, old parser/schema removal or
graph-backed replacement, duplicate fixture cleanup, CLI, docs, skills,
generated views, dependency edges, and applicable static validation in one
atomic integration. The rows below are internal dependency order, not
file-sized or finding-sized repair slices. Split is permitted only for an
actual write conflict or an unresolved predecessor gate, and any split must
preserve one-writer integration and the same source-to-consumer ordering.
The writer works one ordered unit, not parallel file/findings/test slices.
Source mechanism and store validation come first; consumer regression/property
coverage is added last only if the mechanism has no existing oracle.

### Source and store mechanism (`KG-SRC`)

- Add `rust/agent-canon/src/graph.rs` with the identifiers in the naming plan.
  Its `pub(crate) fn run(args: &[String]) -> i32` copies the existing
  `structured_analysis::run` control shape: `args.first()`, then
  `match command.as_str()` with literal `"build"`, `"status"`, `"query"`, and
  `"context"` arms calling `run_build(&args[1..])`,
  `run_status(&args[1..])`, `run_query(&args[1..])`, and
  `run_context(&args[1..])`; help aliases and wildcard usage return `2` and
  create no public row.
- Modify the current manual-dispatch `rust/agent-canon/src/main.rs` by adding
  exactly `mod graph;` and the arm
  `if args.len() >= 2 && args[1] == "graph" {
  std::process::exit(graph::run(&args[2..])); }`, preserving the surrounding
  repeated `if` shape. Delete the current public
  `if ... args[1] == "dependency-manifest"` arm and remove that command from
  the usage string; `mod dependency_manifest;` remains because graph build
  calls its crate-private producer API. Add
  `graph <build|status|query|context>` to the usage string. No command enum,
  derive macro, or alternate dispatch abstraction is introduced.
- Reduce `rust/agent-canon/src/dependency_manifest.rs` to the one complete-file `ManifestParser`, `capture_snapshot`, source identities, source exclusions, declarations, surface relations, and `SourceUniverse`. Remove `HEADER_SCAN_LINES`, `contains_manifest_marker`, normalized transport, R2 registry/attestation/fingerprint schema, and unused fixed-point/transport test machinery. Add `manifest_present: bool` and `source_span: Option<SourceSpan>` to the current `ManifestAst {contract,responsibility,coverage,dependencies,source_span}` record; `ManifestParser::parse` is the only marker/header parser and consumes the complete file through its end marker. Its exact no-manifest rule is: if the complete file contains no `@dependency-start`, return `ManifestAst {manifest_present:false, contract:"", responsibility:"", coverage:[], dependencies:[], source_span:None}` with no diagnostic; if a start marker exists, parse through its matching `@dependency-end`, and a malformed header or missing end marker is a `ManifestError`/`build-failed`. `capture_snapshot` converts `manifest_present:false` to a source record with zero `D` declarations and the normal source hash; ordinary files therefore contribute to `P(S)` without becoming malformed-manifest facts. `None` is the only absent-span representation; it is never converted to a zero span or Graph DSL offset. Update all current constructors/equality tests for the added field.
- Modify `rust/agent-canon/src/structured_analysis.rs` to expose the existing Graph DSL materializer/validator as a narrow crate-private adapter used by `graph.rs`; remove `has_dependency_manifest`, `dependency_manifest_values`, `dependency_coverage_rules`, and the bounded header constants. Its inventory remains metadata-only; owner/dependency facts enter the Graph DSL from the authoritative parser and producers. Do not create a second schema.
- Modify `rust/agent-canon/src/semantic_index.rs` only to expose existing `ContextCell` evidence to the graph context adapter; embeddings and index ownership remain unchanged.
- Modify `tools/agent_tools/generate_agent_runtime_dashboard.py` in the same source-first unit: keep `agent_runtime_dashboard.v1` and its existing readers as the sole runtime producer; make `read_candidate_selection_resets` return the exact accepted/reset plus typed-rejection result; add the requested `RuntimeMeasurement` fields to the existing API; repair the dashboard's canonical token-producer ingestion so `comparison_count=0` is an explicit missing-evidence diagnostic; and make hook attribution ownership explicit at the existing hook event writer while preserving dashboard context-attribution as a non-authoritative count. Do not add a logger, raw-event schema, or graph-side runtime parser.
- Modify `tools/agent_tools/compare_codex_token_footprints.py`, `tools/agent_tools/workflow_monitor.py`, and their owning docs/tests only where needed to expose the existing canonical token/lifecycle evidence fields to the dashboard; reuse `TokenFootprint` and `append_monitoring` rather than introducing a duplicate token record. Add dashboard tests for malformed candidate paths, zero-versus-missing token comparisons, 2,028 missing workflow entries, and every `RuntimeMeasurement` field before graph consumer regression/property tests.
- Modify `.codex/hooks/skill_usage_logger.py::append_skill_usage_entry` and `.codex/hooks/hook_event_log.py::HookLogContext.append` as the single workflow-attribution write boundary; preserve the existing event JSONL and fields, enrich every hook event with the canonical workflow context when available, and retain an explicit missing-attribution count when unavailable. Reuse `tools/agent_tools/runtime_log_paths.py::hook_results_dir` to select the baseline log set. Do not add a graph-side event reader or a second attribution schema.
- Consume, without reparsing, `import_responsibility.py`, `responsibility_scope.py`, the TSV artifact produced by `scan_code_dependencies.sh`, structured-analysis metadata inventory, the JSON artifact produced by `tool_catalog.py`, and semantic-index outputs. `scan_code_dependencies.sh` and `tool_catalog.py` are producer-only: graph build invokes each once, captures its artifact, and no graph consumer invokes either or reparses either. `search_index.py` is downstream-only and is not a build input. Language/parser/compiler/config/build facts remain with their current authoritative tools.
- Modify `tools/agent_tools/scan_code_dependencies.sh` to add the explicit `--paths-file <file>` mode used by graph build; the file is authoritative even when empty, a missing file is an error, and the existing `git ls-files` default remains available only to non-graph standalone callers. Add source-owned scanner tests for nonempty, empty, missing, malformed-path, and marker-count cases before graph consumer tests.

Invariants: one parser, full-file scan to the manifest end marker, producer
provenance on every explicit relation, no inferred edge in `R`, and graph
materialization through the existing Graph DSL tables. `graph.rs` calls exactly
`materialize_graph_store(&Connection, &GraphSourceScope, &[GraphFact], &[GraphProjection], &[GraphDiagnostic], &[ProducerArtifact], &GraphIntegrationRecord, &str) -> Result<(), GraphError>` after `initialize_graph_schema`; the final `&str` is the deterministic HEAD-derived `created_at`. That function inserts existing `documents`, `nodes`, `edges`, `diagnostics`, and `metadata` rows, including producer artifacts, dirty/pin/tool fingerprints, and canonical `integration_record`, and is the only graph-specific materialization boundary.

GraphFact endpoint identity is fixed: source paths use
`node:source:<logical_id>`; owner/scope entities use
`node:owner:<canonical_owner>`; catalog/public selectors use
`node:<kind>:<surface_id>`; and all other producer entities use
`node:<relation-kind>:<canonical_selector>`. `GraphFact.from` and non-null
`to` contain these stable node IDs, while `payload_json` retains the original
parent-relative paths/selectors. The relation-to-layer map is
`dependency|import|include|symbol|call|containment|document|pin|view|generated|submodule→source`,
`owner|scope→owner`, `catalog→catalog`, and `public→public`. A missing target
is `to=null` only in a diagnostic fact and is never inserted into `R`; an
accepted `R` fact must have a resolved target node. Reverse projections reuse
the same endpoint IDs in swapped order, use edge ID `reverse:<fact-id>`, set
`inferred=true`, and preserve the original evidence reference. Projection
membership uses `node:projection:<projection-id>` and edges to the member node.
Graph DSL's existing `source_start`/`source_end` fields are zero-based Unicode
scalar-value character offsets, not a new byte schema. Current manifest
`SourceSpan.start_column`/`end_column` values are one-based UTF-8 byte columns
(`end_column` is exclusive, as the current parser uses `line.len() + 1`). The
adapter reads the exact UTF-8 source bytes, requires each column minus one to
be a valid UTF-8 boundary, counts Unicode scalar values in all preceding bytes
including their preserved newline characters, then counts scalar values in the
line prefix to compute the zero-based Graph DSL offset. A non-boundary,
missing-line, or inconsistent end span is `Validation{stage="source-span"}`
and aborts the candidate; the worker cannot choose a lossy replacement.
The original one-based byte line/column span remains in payload JSON. A
`GraphFact.source_span=None` fact uses `0,0` only as the existing Graph DSL
non-evidence sentinel and retains `source_span:null` in payload JSON; the
no-manifest source record is not materialized as an evidence fact at all.
No line number is written into a character-offset field, and the graph does not
introduce a parallel offset convention.

`GraphQueryFact.from`/`to` remain IDs in every relation family. The query
projection always returns the endpoint `GraphNode` rows needed to resolve
those IDs. The canonical endpoint selector is `GraphNode.selector`: source
families use the normalized source path; `owner|scope` use the canonical owner
selector and also set `owner`; `catalog|public` use the producer surface ID;
all other families use the producer's canonical selector. `GraphNode.path` is
the source path for source nodes and `null` for non-path entities. A consumer
joining a fact to `nodes[fact.from]` or `nodes[fact.to]` therefore obtains the
exact path only when that endpoint is a source node and obtains the exact
owner/surface selector for the other families; it never treats an opaque node
ID as a path. `GraphClaimConsumer` uses this join for dependency facts, where
both endpoints must be source nodes; a missing endpoint row is an unresolved
graph diagnostic, not a filesystem lookup.

The materializer field map is fixed. It inserts one deterministic document row
`id=doc:knowledge-graph`, `path=.agent-canon/knowledge-graph/graph.sqlite`,
`title=AgentCanon knowledge graph`, `kind=knowledge-graph`, and
`created_at=<HEAD commit timestamp>`; no wall-clock value is used. Each unique
endpoint becomes a node with its stable endpoint ID, and each `GraphFact`
becomes an evidence node with `id=fact:<stable-id>`, that document ID,
`layer=adapter:graph-fact`, `kind`, `label=<canonical endpoint/selector>`,
`text=<canonical endpoint/selector>`,
`source_start=<Graph DSL character offset from source_span or 0>`, `source_end=<Graph DSL character offset from source_span or 0>`,
`confidence=1.0` for explicit producer facts or `0.5` for inferred projections,
and payload JSON containing owner, producer, source span, authority, endpoint
IDs, and evidence reference. Each accepted relation becomes an edge with its stable
edge ID, layer/kind, `from_node_id`/`to_node_id`, `order_kind=none`,
`confidence=1.0`, `evidence_node_id=<source fact node or NULL>`, and the full
producer payload. Projection membership is represented as `layer=adapter:graph-projection`
nodes/edges whose payload includes `projection_id` and `member_id`; no new
table is introduced. Each `GraphDiagnostic` becomes a diagnostics row with
`layer=diagnostics`, `diagnostic_id=<GraphDiagnostic.id>`,
`target_node_id=<matched node or empty string>`,
`target_edge_id=<matched edge or empty string>`, severity `blocker|warn|info`,
rule=`code`, message=`reason`, and `suggested_action_json={"action":...,"owner":...,"retryable":...,"graph_diagnostic":<canonical GraphDiagnostic JSON>}`. The exact
target rule is: resolved `path` maps to its endpoint node, resolved `target`
maps to the target endpoint node, and a relation diagnostic with a materialized
fact maps to `fact:<id>`'s edge; absent matches remain empty strings. Metadata uses the
fixed keys `schema_version`, `root`, `profile`, `source_snapshot_profile`, `snapshot_head`,
`dirty_fingerprint`, `agent_canon_pin`, `input_fingerprint`,
`graph_fingerprint`, `producer_artifacts`, `producer_artifact_payloads`, `source_scope_counts`,
`relation_counts`, `tool_versions`, `integration_record`, and `created_at`; `integration_record` is the canonical JSON serialization of `GraphIntegrationRecord` and is the only metadata key a consumer verifies. Values are canonical
JSON or strings sorted by key. These mappings satisfy the existing NOT NULL,
confidence, and order-kind validators.

### Consumers, docs, skills, and public edges (`KG-CONSUME`)

- Convert `tools/agent_tools/check_design_doc_claims.py` to the graph consumer route described above.
- Convert `tools/agent_tools/vector_search.py` context dependency expansion,
  `tools/agent_tools/search_index.py` owner extraction,
  `tools/agent_tools/search.py` coordinated `header-deps` provider, and
  `tools/agent_tools/render_dependency_manifest_graph.py` to graph queries;
  remove their duplicate manifest parsing. Keep `tool_catalog.py` as the
  catalog/public producer and remove only its local dependency-header marker
  scan; it does not query the graph.
- Convert `tools/agent_tools/tool_drift.py` to consume graph dependency facts
  under the symbol-complete contract below; in
  `tools/agent_tools/prose_reasoning_graph.py`, retain the prose Graph DSL
  parser but delete any dependency-header parsing and use graph queries for
  dependency evidence.
- Convert `tools/agent_tools/check_dependency_headers.py`, `check_dependency_header_format.sh`, `check_dependency_graph.sh`, `scan_dependency_headers.sh`, and `run_repo_dependency_review.sh` into thin graph consumers. Their output labels may remain for workflow compatibility, but they cannot parse or store facts independently. `scan_code_dependencies.sh` is deliberately excluded from this consumer group and remains the single code-relation producer invoked by `graph build`.

The Python changed-file checker boundary is exact. In
`check_dependency_headers.py`, retain `CHECKABLE_SUFFIXES`, `SKIP_PREFIXES`,
`BINARY_SNIFF_BYTES`, `build_parser`, `git_lines`, `changed_paths`,
`repo_relative`, `is_binary`, `should_check`, the accepted
`--allow-frontmatter` compatibility flag, and the existing
`DEPENDENCY_HEADERS=pass|fail` text/exit contract. Delete `HEADER_SCAN_LINES`,
`CONTRACT_REGISTRY`, `CONTRACT_LINE_RE`, `TOML_STRING_RE`,
`has_dependency_manifest`, `has_dependency_header`, `strip_manifest_line`,
`manifest_lines`, `registry_candidates`, `contract_registry_path`,
`allowed_contract_kinds`, and `contract_kind_findings`; registry validation is
performed once by `source-snapshot`/`ManifestParser` during graph build.

After selecting, normalizing, deduplicating, and sorting checkable `RepoPath`
values, the checker invokes through `GraphClient` exactly the subprocess arrays
`[<root>/vendor/agent-canon/tools/bin/agent-canon, graph, status, --root,
<root>, --profile, default, --format, json]` and, for each selected path,
`[<root>/vendor/agent-canon/tools/bin/agent-canon, graph, context, --root,
<root>, --profile, default, --format, json, --path, <repo-path>]`, always with
`cwd=<root>`. Status must be `fresh` and contain a non-null
`GraphIntegrationRecord` with `verified=true`, `profile=default`, and
`source_snapshot_profile=parent`; otherwise print
`DEPENDENCY_HEADERS=fail`, one
`- graph-integration-unverified: status=<state>; reason=<reason>` line, and
return `1`. The checker never invokes `graph build`.

For a selected path, `graph context` returns the source-snapshot projection as
exact `GraphContextItem` rows: one `kind=manifest.present` with value
`true|false`; when true, exactly one `kind=manifest.contract` and exactly one
`kind=manifest.responsibility`; all have `source_store=manifest`,
`producer=source-snapshot`, `source_path=<repo-path>`, the parser's source span
when present, its producer evidence reference, and `authority=ManifestParser`.
`manifest.present=false` maps to the existing finding
`<repo-path>: missing top dependency manifest block`. Missing, duplicate, or
wrong-producer rows map to
`<repo-path>: invalid graph dependency manifest evidence: <graph-code>`.
A valid `manifest.present=true` needs no local contract-kind parser because the
producer already validated the contract registry. A non-fresh context, graph
exit `1|3|4`, launch/JSON/schema/join failure, or malformed projection yields
`DEPENDENCY_HEADERS=fail` and return `1` with the typed graph status/reason;
argparse usage remains exit `2`. No filesystem/header fallback is permitted.

The shell consumer boundary covers only existing shell entrypoints. Each
converted shell entrypoint runs with `set -euo pipefail`,
`cwd=<parent-root>`, and executable
`<parent-root>/vendor/agent-canon/tools/bin/agent-canon`; it passes argument
arrays without shell interpolation and always appends `--root <parent-root>
--profile default --format json`. `check_dependency_header_format.sh` invokes
`graph status` then, when status is `fresh`, uses `graph context --path` for its
selected files and validates the same manifest items; it preserves its label
but owns no tokenizer. `check_dependency_graph.sh` invokes `graph status` then
`graph query --all --relation all --direction both --depth 0`; `scan_dependency_headers.sh`
invokes `graph status` then `graph query --all --relation dependency --direction both --depth 0`; and
`run_repo_dependency_review.sh` invokes `graph status` followed by both the
`graph query --all --relation dependency --direction both --depth 0` and
`graph query --all --relation owner --direction both --depth 0`.
`render_dependency_manifest_graph.py` uses the identical executable/CWD rule
through `GraphClient`, not a shell wrapper. A valid nonzero JSON response is
forwarded with its `status`, diagnostics, and exit code; launch failure,
missing executable, invalid JSON, or wrong schema is a consumer failure. No
shell consumer reads headers, invokes `git ls-files` for facts, opens
`graph.sqlite`, or treats a non-fresh response as evidence.

The coordinated-search replacement is also exact. Change
`SearchCorpus.dependency_edges` from
`tuple[vector_search.DependencyEdge, ...]` to
`tuple[GraphDependencyFact, ...]`; retain documents, tool entries, semantic
cards, Python symbols/call edges, provider scoring, `ProviderHit`, `Candidate`,
and output ordering. `load_corpus` must not call
`vector_search.parse_dependency_edges`. When `header-deps` is selected it
performs exactly one graph request equivalent to
`[<executable>, graph, query, --root, <root>, --profile, default, --format,
json, --all, --relation, dependency, --direction, both, --depth, 0]` and loads
only `GraphResponse.dependency_facts`; when that provider is not selected it
makes no graph call. `header_dependency_hits` keeps the current source/target
scoring behavior and uses the searchable tuple
`source,target,direction,kind,reason`; its evidence string additionally carries
`producer`, `source_path`, `source_span`, `evidence_ref`, and `authority` from
the typed graph row. Non-fresh valid graph JSON, endpoint/detail join failure,
or `GraphClientError` prints `AGENT_SEARCH=fail` plus
`AGENT_SEARCH_ERROR=graph:<status-or-code>:<reason>` and returns the underlying
graph exit `1|3|4` (or `1` for adapter failure), with no direct-parser fallback.
`vector_search.py` remains the owner of text/TF-IDF and Python symbol/call
facts, not manifest dependency facts.

The `tool_drift.py` disposition is symbol-complete. Delete `ManifestEdge`,
`HEADER_SCAN_LINES`, `MANIFEST_FIELD_COUNT`,
`MANIFEST_REASON_MAX_SPLIT`, `has_dependency_manifest`,
`strip_manifest_line`, `repo_relative`, `normalize_target`, and
`manifest_edges`. `repo_relative` is called only by the deleted
`normalize_target` and `manifest_edges`, so delete the now-unused `os` import
in the same source edit. Retain
`LinkCheck`, `TextCheck`, `ToolContract`, `Finding`, `resolve_repo_path` only
for tool/link/text file existence, the YAML catalog/stale/legacy checks,
`opposite_direction`, `compatible_reverse_kind`, direct/reverse matching,
`check_link`, `check_text`, renderers, and CLI. Generalize the retained edge
type annotations to `GraphDependencyFact`; `run_checks` performs one
`GraphClient.query(path=None,all=True,relation="dependency",direction="both",
depth=0)` and passes `GraphResponse.dependency_facts` to link/reverse-kind
checks. Delete only the `check_catalog_entries` branch that emits
`missing-dependency-header`; `check_dependency_headers.py` owns that oracle,
while catalog mapping/entry/stale/legacy findings remain. Non-fresh or invalid
graph results append exactly
`Finding("graph-dependency-evidence-unavailable","graph",
".agent-canon/knowledge-graph/graph.sqlite",
"status=<state>;reason=<reason>")`, produce the existing
`TOOL_CONVENTION_DRIFT=fail`/JSON failure form, return `1`, and stop before
contract link evaluation; they never silently produce an empty edge set.
- Update `documents/dependency-manifest-design.md`, `documents/structured-analysis/dependency-header-analysis.md`, `documents/structured-analysis/graph-dsl.md`, `documents/tools/check_design_doc_claims.md`, `documents/tools/render_dependency_manifest_graph.md`, `tools/README.md`, and `documents/tools/README.md` to describe the one parser, four CLI operations, Graph DSL reuse, completeness sets, and no-MCP boundary; refresh applicable generated/root views through their owning sync route rather than hand-editing generated output.
- Update `agents/canonical/CLI_ENTRYPOINTS.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/workflows/implementation-waterfall-workflow.md`, `agents/agents_config.json`, `agents/skills/dependency-analysis.md`, `agents/skills/prose-reasoning-graph.md`, `.agents/skills/prose-reasoning-graph/SKILL.md`, and all affected dependency headers to route `graph` and remove R2/binder/transport claims.
- Update `tools/catalog.yaml` to register the single graph CLI and graph-consumer checker; remove catalog entries for `bind_r2_scope.py` and `dependency_manifest_records.py`.
- Update the owning runtime-dashboard/log-analysis docs, workflow-monitoring contract, generated dashboard/root views, and affected dependency headers to document `RuntimeMeasurement`, typed selection-path rejection, hook-owner attribution, zero-versus-missing token evidence, and graph context provenance. The existing `agent_runtime_dashboard.v1` API and canonical token/hook event producers remain the only logger/schema authorities; no second runtime route is added.

### Dirty and stale tests/fixtures (`KG-TEST-LAST`)

First port the dirty semantic intent into the source mechanism and consumer:
the dirty claim-token additions become graph-backed path/evidence tests; the
dirty Rust/Python manifest changes become complete-file parser and producer
join tests; dirty documentation becomes the new CLI/operator wording.

After those tests pass, remove the obsolete transport matrices and binder
tests. Delete these branch fixtures because they encode the rejected private
transport authority: `tests/fixtures/dependency_manifest/parser_conformance.jsonl`,
`relation_reconciliation.jsonl`, `source_universe.jsonl`,
`transport_conformance.jsonl`, `tests/fixtures/knowledge_graph/freshness_atomic_closure.jsonl`,
`query_kind_registry.jsonl`, and the dirty
`tests/fixtures/dependency_manifest/normalized_record_set.v1.jsonl`,
`relation_registry.v1.json`, `source_snapshot.v1.jsonl`.

Replace them with only the smallest graph-owned cases:
`tests/fixtures/knowledge_graph/graph_contract.jsonl` for scope, producer
provenance, unresolved/ambiguous sets, reverse-edge closure, atomic failure,
and freshness; and `tests/fixtures/knowledge_graph/context_evidence.jsonl`
for exact owner/source/dependency context. These are new fixture names, not a
second schema.

Add two small producer grammar fixtures, not a matrix:
`tests/fixtures/tool_catalog/main_manual_dispatch.rs` contains `mod graph;` and
the exact current-main-style graph arm, and
`tests/fixtures/tool_catalog/graph_manual_dispatch.rs` contains the exact
`args.first()` plus four literal operation arms. `test_tool_catalog.py`
generates negative mutations in its temporary directory rather than adding
fixture permutations: comment/usage-only text, enum-derived dispatch,
duplicate graph/operation arms, missing `mod graph;`, wrong `args[1]` or
`&args[2..]` index in `main.rs`, and wrong `&args[1..]` operation slice in
`graph.rs`. The oracle requires four sorted public rows whose primary spans are
the four graph-module arms and whose secondary spans include the one main arm;
each negative mutation returns exactly
`public_surface.rust_dispatch_invalid` or
`public_surface.rust_dispatch_ambiguous` and no partial public row.

After the source and graph-client mechanisms pass, update
`test_check_dependency_headers.py` with a fake executable/adapter recording the
exact status plus one-context-per-sorted-path arrays, `manifest.present` false,
valid present/contract/responsibility evidence, duplicate/wrong-producer
evidence, and non-fresh/no-fallback cases. Preserve the current selection and
`DEPENDENCY_HEADERS` assertions. Update `test_search.py` with a graph-client
spy proving zero graph calls without `header-deps`, exactly one all-dependency
query when selected, typed evidence provenance, non-fresh failure, and a
residual assertion that `search.py` no longer names the direct parser call;
retain current text/tool/code-provider tests. Update `test_tool_drift.py` with
canonical `GraphDependencyFact` fixtures for the existing missing-link,
missing-reverse, and kind-mismatch findings, catalog behavior without a local
header finding, one-query behavior, non-fresh failure, and the symbol residual
oracle below. These are public consumer regressions added last, only where the
source/adapter tests do not already exercise the oracle.

Add Rust source tests for the profile adapter and dispatch before those Python
consumer tests: omitted profile and explicit `default` construct byte-equal
`SnapshotRequest` values/fingerprints with `profile="parent"`; public
`--profile parent` exits `2`; the captured request has the resolved parent root
and candidate snapshot path; a snapshot header or stored integration mapping
mismatch is rejected before fact projection. A CLI smoke test proves the
manual main arm reaches each of the four graph operations and the removed
public dependency-manifest route is unknown.

Update `tests/agent_tools/test_dependency_manifest_tools.py` to test the one
parser and graph CLI/store contract; update
`tests/agent_tools/test_check_design_doc_claims.py` to test the thin consumer;
update branch-only assertions in `test_agent_team_templates.py`,
`test_task_start_and_close.py`, and `test_waterfall_gate_check.py` only where
they refer to the removed R2 route. Remove R2-specific tests from those files;
retain unrelated task/runtime coverage.

The worker must preserve user-owned dirty intent by recording the semantic
cases before deletion, never using destructive Git cleanup, and deleting the
obsolete files only after their replacement source mechanism and consumer
oracles pass. No dirty file is silently reverted.

### Branch composition rule

`9ba4bba5` is an active-design-packet change rather than graph authority. The
writer must inspect its hunks in `agents/agents_config.json`,
`agents/canonical/CLI_ENTRYPOINTS.md`, `agents/canonical/CODEX_WORKFLOW.md`,
`agents/workflows/implementation-waterfall-workflow.md`,
`tools/agent_tools/agent_team.py`, `tools/agent_tools/bootstrap_agent_run.py`,
`tools/agent_tools/task_start.py`, `tools/agent_tools/waterfall_gate_check.py`,
and their related tests. The four helper paths
`tools/agent_tools/agent_team.py`, `bootstrap_agent_run.py`, `task_start.py`,
and `waterfall_gate_check.py` are inspection-only for this graph unit: no
graph-specific implementation or dependency-header edit is authorized there.
Unrelated active-packet changes are excluded from the graph PR and preserved
as user-owned history for a separate PR. This is a composition decision, not
permission to reset or discard the current checkout.

The graph PR must include the graph portions of `ecacb84b`, `24c878b4`,
`0a7cc98a`, and `607c8e81`, then delete their private transport/binder routes.
It must not claim that the current branch is already a coherent implementation
or that a PR exists.

### Current dirty-path disposition

Current checkout evidence is intentionally separated into clean branch history
and user-owned dirty state:

| State | Exact evidence | Design consequence |
| --- | --- | --- |
| Branch | `codex/knowledge-graph-cli`, ahead of `origin/codex/knowledge-graph-cli` by 2 commits; the requested `origin/main..HEAD` comparison includes `ecacb84b`, `24c878b4`, `0a7cc98a`, and `607c8e81` and is approximately 18k lines of graph/R2 transport work. | This one unit consolidates the branch into the later coherent graph/source PR; no historical R2 route is retained. |
| Modified dirty paths | `documents/tools/check_design_doc_claims.md`, `rust/agent-canon/src/dependency_manifest.rs`, `tests/agent_tools/test_check_design_doc_claims.py`, `tests/agent_tools/test_dependency_manifest_tools.py`, `tools/agent_tools/bind_r2_scope.py`, `tools/agent_tools/check_design_doc_claims.py`, `tools/agent_tools/dependency_manifest_records.py`. | Preserve each semantic intent through the disposition table before source-first cleanup. |
| Untracked dirty fixtures | `tests/fixtures/dependency_manifest/normalized_record_set.v1.jsonl`, `relation_registry.v1.json`, `source_snapshot.v1.jsonl`. | Treat as user-owned dirty inputs; port semantic cases, then delete obsolete private transport matrices only after source checks pass. |
| Parent/untracked runtime-result state | `experiments/_template/result/readonly_agent_log_analysis_dashboard/`, `readonly_agent_log_analysis_dashboard2/`, `readonly_agent_log_analysis_ensure/`, and `readonly_agent_log_analysis_status/` when exposed by the parent checkout (the submodule may not list them). | Preserve byte-for-byte as user-owned runtime evidence; read them only through the canonical dashboard producer, exclude their paths from `P(S)` via the explicit `X(S)` rule, and never delete/create/include them in the graph PR. Their presence or absence does not widen this one-unit write scope. |
| Clean branch fixtures | `parser_conformance.jsonl`, `relation_reconciliation.jsonl`, `source_universe.jsonl`, `transport_conformance.jsonl`, `tests/fixtures/knowledge_graph/freshness_atomic_closure.jsonl`, and `query_kind_registry.jsonl` are branch-history fixtures, not current dirty files. | Reuse semantic cases where they cover the new mechanism; remove obsolete transport portions only after source/public validation. |

| Current dirty path | Disposition in this one unit |
| --- | --- |
| `tools/agent_tools/check_design_doc_claims.py` | Keep only the graph-owned `GraphClaimConsumer` path, `ClaimTokenClass` input classification, and `CheckResult` rendering; delete/replace all old ad-hoc parser/schema/claim-evaluation logic. It must verify `GraphIntegrationRecord` through canonical `graph status` before calling `query`/`context`, otherwise it returns `graph-integration-unverified`. |
| `documents/tools/check_design_doc_claims.md` | Rewrite as the graph-consumer contract, including fresh-status refusal and resolvable-path versus graph-evidence semantics. |
| `tests/agent_tools/test_check_design_doc_claims.py` | Port dirty token-classification cases to graph-backed fixtures; retain only consumer regression/property cases after the mechanism is validated. |
| `tools/agent_tools/bind_r2_scope.py` | Delete after its semantic boundary is represented by graph build/status and its catalog/docs/dependency edges are removed. |
| `tools/agent_tools/dependency_manifest_records.py` | Delete after its dirty decoder/projector cases are represented by Graph DSL rows and producer artifacts; it is never copied into `graph.rs`. |
| `rust/agent-canon/src/dependency_manifest.rs` | Integrate the dirty complete-file parser/producer changes, remove the line cap and private transport types, and retain the single authoritative parser. |
| `tests/agent_tools/test_dependency_manifest_tools.py` | Port dirty parser/producer cases to the source mechanism and graph CLI/store contract, then remove only obsolete R2/transport assertions. |
| `tests/fixtures/dependency_manifest/normalized_record_set.v1.jsonl` | Delete after its semantic cases are ported; it is a private transport fixture, not a graph input. |
| `tests/fixtures/dependency_manifest/relation_registry.v1.json` | Delete after its relation/provenance cases are ported to the Graph DSL fixture. |
| `tests/fixtures/dependency_manifest/source_snapshot.v1.jsonl` | Delete after source-scope/fingerprint cases are ported to the graph contract fixture. |

This table is the preservation record for the user-owned dirty worktree: the
writer captures each semantic case in the source or consumer oracle before any
obsolete file or matrix is removed, never resets or reverts the dirty paths,
and leaves unrelated dirty intent outside this graph PR.

### Phase contract for `KG-N1`

The literal source clause is phase-scoped and is not rewritten by this brief.
During the requirements-update phase, `KG-N1` forbids editing the design brief
while requirements are being formed. During this design-review phase, the
explicit user request authorizes this brief as the sole write target; no source,
config, test, fixture, or other artifact is edited. After a fresh approve of
this exact brief, the implementation phase may edit only the explicit file plan
and its source-first validation surfaces; that later scope is a worker contract,
not permission for this turn and not a relaxation of the current-turn rule.

## Explicit deletion list

The following are deleted or stripped; none may survive as a public or hidden
fact authority:

- `tools/agent_tools/bind_r2_scope.py` and its catalog/docs/dependency edges.
- `tools/agent_tools/dependency_manifest_records.py` and its catalog/docs/dependency edges.
- Rust normalized-record transport types/functions and all `RelationNormalizer` registry/attestation/byte-schema code in `rust/agent-canon/src/dependency_manifest.rs`.
- Public `agent-canon dependency-manifest normalize` route and any R2 aliases.
- `ManifestParser` line cap `HEADER_SCAN_LINES` and every duplicate Python/shell manifest parser implementation.
- `check_dependency_headers.py`'s `HEADER_SCAN_LINES`, regex/TOML registry
  decoder, manifest-line functions, and local contract-kind findings; its
  path-selection and result shell remain as the graph-backed consumer.
- `search.py`'s direct `vector_search.parse_dependency_edges` call and
  `vector_search.DependencyEdge` corpus type; coordinated scoring/output remain
  over `GraphDependencyFact`.
- `tool_drift.py::{ManifestEdge,HEADER_SCAN_LINES,MANIFEST_FIELD_COUNT,
  MANIFEST_REASON_MAX_SPLIT,has_dependency_manifest,strip_manifest_line,
  repo_relative,normalize_target,manifest_edges}`, its now-unused `os` import,
  and only the catalog-local
  `missing-dependency-header` branch; retained drift policy becomes a graph
  consumer.
- Any command-enum/derive alternate for graph dispatch and any fixture matrix
  for alternate Rust dispatch shapes; the two positive manual-dispatch
  fixtures plus generated negative mutations are the only extractor fixtures.
- Any graph construction that passes public profile `default` directly into
  `SnapshotRequest.profile`; the sole adapter value is producer profile
  `parent`.
- R2/transport/normalized-record fixture matrices listed in `KG-TEST-LAST`.
- Binder, normalized-record, registry-fingerprint, byte-order, and duplicate Python transport tests after semantic cases are ported.
- Any branch-only config/prompt/workflow wording that treats R2 status, scope manifests, review binders, or normalized transport as graph prerequisites.

No deletion removes the authoritative dependency-header grammar, source snapshot
identity, owner/import producer, Graph DSL store, semantic-index store, or
claim-token path/evidence distinction.

## Authority and stale-packet handling

The current user request and this post-revision design brief are the governing
contract. The exact current-contract identifier is the body digest carried by
the authority marker above; the full-file review identifier is reported at
handoff. `implementation_request.txt`
and `implementation_surface_route.txt` are historical routing artifacts bound
to the superseded SHA
`5febd536a44fe5d3f1e7fe5ffecc028c8e3f0e2658182790393fb20728449f87`;
their `AC-*` clauses, allowed paths, forbidden parent-graph route, and
semantic-index prohibition are not implementation constraints for this graph
unit. The writer reads them only to record and reject that stale route. No
worker may use their old SHA or route to narrow the current request.

### Canonical predecessor integration gate

The body marker and same-SHA review results identify this pending design only;
they are not implementation authorization and must never be consumed by a
successor design as a mutable predecessor. Successor designs consume only the
canonical archived integration record produced after source integration:
`reports/agents/20260712-090608-context-packettool-skill-routing/predecessor_integration.knowledge_graph.json`,
with the same-snapshot sibling `archive_manifest.json`. The record schema is
`agent_canon.predecessor_integration.v1`, and its exact generic required fields
are the canonical thirteen: `schema_version`, `unit_id=knowledge_graph`,
`design_path`, `design_sha256`, `approve_review_path`, `approve_review_sha256`,
`source_pr_url`, `source_pr_number`, `integrated_source_oid`,
`observed_target_main_oid`, `produced_at`, `producer`, and `artifact_sha256`.
`approve_review_path` is the canonical approval-set manifest produced and
parsed by `github_publish.py`; that manifest binds the fresh same-SHA detailed
design and document-flow approvals in their canonical order. Those review
paths and hashes are not extra predecessor-record fields, and this design
defines no competing review-set schema. `design_sha256` is the
full-file SHA-256 of the approved design bytes including the authority-marker
line; the marker-excluded body SHA is the review-target identity only and is
also recorded in the approval review, never substituted for `design_sha256`.
`approve_review_sha256` is the full-file SHA-256 of the canonical approval-set
manifest. The individual detailed-design and document-flow approval hashes are
members of that manifest's bound approval entries, not predecessor-record
fields. The explicit verifier is:
`python3 tools/agent_tools/github_publish.py verify-predecessor-integration
--record <explicit-record> --archive-manifest <same-snapshot>/archive_manifest.json
--expected-unit-id knowledge_graph`.

The verifier is predecessor-owned and is not required to exist in the current
checkout before the predecessor source PR is integrated; an absent verifier or
record therefore remains a hard pending gate for a successor, not an invitation
to invent a local check. The predecessor target is fixed to `refs/remotes/origin/main`; caller-selected
refs, filenames, aggregate artifacts, chat/review summaries, or a pending
design SHA are forbidden. A successor may proceed only after the verifier
returns success, the archived record is byte-bound to the same source OID, and
the sibling archive manifest verifies the record hash. Until then the graph
unit reports `successor_predecessor_gate=pending`; no successor design or
successor consumer is authorized. This current brief is the predecessor design:
its implementation handoff is gated by fresh same-SHA detailed-design and
document-flow approval, while the archived record is produced only after its
source PR integrates. This rule is distinct from runtime freshness: once the
graph source PR is integrated, `GraphClaimConsumer` additionally requires the
verified `GraphIntegrationRecord` from `graph status` before evaluating any
claim.

### Prior-finding closure ledger

The active schedule names `DGR-01..DGR-09` and `F-01..F-04` as prerequisites;
they are historical finding IDs, not new implementation authorities. This
ledger closes each against a concrete section and oracle so the next review
does not need to infer whether the old packet was addressed.

| Finding ID | Closure in this brief | Validation evidence |
| --- | --- | --- |
| `DGR-01` | Complete-file `ManifestParser`, `P(S)`, `X(S)`, `U(S)`, and source identity are fixed in the mathematical/source contracts. | 2, 3, 14. |
| `DGR-02` | Relation-kind matrix, reverse-edge index closure, direction/depth query algorithm, and explicit X/A diagnostics replace private closure routes. | 6, 9, 20, 21. |
| `DGR-03` | `GraphFact`, nested evidence schemas, producer artifacts, and source spans bind every explicit relation to an authoritative producer. | 4, 10, 18. |
| `DGR-04` | Canonical/view/generated/submodule identity and `V(G)=normalize(U\\X)` are fixed with pin/view provenance and no duplicate logical node. | 3, 9, 19, 20. |
| `DGR-05` | Finite-set equations, order-independent stable IDs, freshness inputs, and the explicit non-formal-proof boundary are fixed. | 3, 8, 18, 21. |
| `DGR-06` | Four-command CLI, parent DB path, status precedence, exit codes, candidate publication, and all six failure seams are fixed. | 5, 7, 8, 16. |
| `DGR-07` | Graph-backed `GraphClient`, checker/search consumer boundary, exact context evidence, and all relation-family queries are fixed. | 6, 10, 11, 20. |
| `DGR-08` | Canonical docs/skills/catalog/runtime owners, producer-only `tool_catalog.py`, and deletion/reverse-edge closure are listed in the file plan. | 15, 16, 17 plus docs check. |
| `DGR-09` | Source mechanism precedes dirty-case port and public regression/property cases; claim classification and no-fallback findings are fixed. | 2, 11, 17, 21. |
| `F-01` | Required commands are fail-closed: exact CWD, captured exit code, `set -euo pipefail` for shell routes, and no `|| true` in acceptance commands. | 1, 7, 12, 17. |
| `F-02` | The source packet names the current `dependency_manifest.rs` owner and the new `graph.rs`; no nonexistent Rust owner is used. | Source Packet and naming plan; 1, 5. |
| `F-03` | `documents/structured-analysis/graph-dsl.md` is a mandatory source-packet artifact and Graph DSL is the sole storage contract. | 5, 13. |
| `F-04` | The Abstract Design Frame explicitly presents responsibility, concept/layer, non-goal, future, evaluation, and canonical-surface categories before file scope. | 1, 3, 5, 17. |

This ledger records design closure only; it does not claim the final detailed or
document-flow approvals, which remain the required same-SHA gates below.

## Implementation Source Packet

The writer must read all mandatory items below in order. This is a mandatory
packet, not a menu. Optional archival context and the deferred successor gate
are explicitly outside this packet and cannot authorize or block this
predecessor's implementation handoff.

### Required request and design evidence

Packet-ID definitions are part of this mandatory packet before any artifact
reference: `SEARCH-n-N*` and `SEARCH-n-C*` are respectively the negative and
coverage checks for each `SEARCH-1..SEARCH-8`; `F6` is graph population and
provenance, `F7` freshness/materialization, `F8` coverage/reconciliation, `F9`
query/bounded context, and `F10` proof boundary. Each F packet requires the
field-complete tuple `finding_class`, `evidence_cells`, `route_target`,
`instance_partition`, `required_packet`, and `closeout_gate` recorded in the
ledger below.

- This design brief, including clause IDs `KG-1..KG-9` and `BR-1..BR-3`.
- `reports/agents/20260712-090608-context-packettool-skill-routing/graph_architecture_audit.md`.
- `reports/agents/20260712-090608-context-packettool-skill-routing/user_request_contract.md`: current `KG-A..KG-J`, `KG-C1..KG-C10`, must-not-do clauses, coverage symbols, and acceptance evidence.
- `reports/agents/20260712-090608-context-packettool-skill-routing/search_requirements.md`: preserved `SEARCH-1..SEARCH-8`, source-bucket accounting, F6–F10 graph packets, query-plan fields, and proof/freshness/coverage gates.
- `reports/agents/20260712-090608-context-packettool-skill-routing/implementation_request.txt` and `implementation_surface_route.txt`, read only for stale-route classification under the Authority section; neither is a design authority or an implementation-scope source.
- `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt` and `reports/agents/20260712-090608-context-packettool-skill-routing/ci_oop_implementation_request.txt`: predecessor-input sections covering canonical record paths, `agent_canon.predecessor_integration.v1`, fixed `origin/main` target, verifier command, and pending-gate behavior.
- `reports/agents/20260712-090608-context-packettool-skill-routing/dependency-review/dependency_edit_scope.txt` and `dependency_graph.tsv`.
- `reports/agents/20260712-090608-context-packettool-skill-routing/file_surface_inventory.json` and `file_surface_inventory.md`.
- No historical review artifact is a mandatory packet input; fresh same-SHA review outputs are required below and historical files never substitute for them.
- Current branch evidence: `git log --oneline origin/main..HEAD`, `git diff --name-status origin/main..HEAD`, `git status --short`, and the dirty diff for all `BR-2` paths.
- The same `implementation_request.txt` and `implementation_surface_route.txt` stale-route classification is already covered above; do not reread them as a competing scope authority.

The packet identifiers are defined before the index: for each preserved
`SEARCH-1..SEARCH-8`, `SEARCH-n-N*` is the prohibited-route check and
`SEARCH-n-C*` is the positive coverage check. `F6` is graph population and
provenance, `F7` graph freshness and materialization, `F8` coverage and
reconciliation, `F9` query and bounded context, and `F10` proof boundary; their
required fields are the six `finding_class`/`evidence_cells`/
`route_target`/`instance_partition`/`required_packet`/`closeout_gate` columns
in the ledger below. Before reading source files, apply this packet-ID index;
the full disposition
table later in this brief is the same ledger used by the Side-Effect Map and
Trace. `SEARCH-1-N*`/`SEARCH-1-C*` map to `SEM-02,SEM-09`; `SEARCH-2-N*`/
`SEARCH-2-C*` to `SEM-04`; `SEARCH-3-N*`/`SEARCH-3-C*` to `SEM-03,SEM-10`;
`SEARCH-4-N*`/`SEARCH-4-C*` to `SEM-04,SEM-05,SEM-07`;
`SEARCH-5-N*`/`SEARCH-5-C*` to `SEM-05,SEM-06`;
`SEARCH-6-N*`/`SEARCH-6-C*` to `SEM-02,SEM-08,SEM-09`;
`SEARCH-7-N*`/`SEARCH-7-C*` to `SEM-05,SEM-06,SEM-08`; and
`SEARCH-8-N*`/`SEARCH-8-C*` to `SEM-05,SEM-07,SEM-10`.
`F6` maps to `SEM-01,SEM-04`, `F7` to `SEM-06`, `F8` to `SEM-05`,
`F9` to `SEM-03,SEM-07,SEM-10`, and `F10` to `SEM-05,SEM-08`. Negative checks remove
the prohibited route; coverage checks require the producer, owner, evidence,
freshness, and closeout fields named by those map rows.

### Deferred successor-only gate (outside the mandatory packet)

For a successor handoff, the source packet requires a read-only predecessor gate
check: read the explicit archived
`predecessor_integration.knowledge_graph.json` and its same-snapshot
`archive_manifest.json`, then run
`python3 tools/agent_tools/github_publish.py verify-predecessor-integration
--record <explicit-record> --archive-manifest <same-snapshot>/archive_manifest.json
--expected-unit-id knowledge_graph`. If either archived path is unavailable or
verification is not successful, record `successor_predecessor_gate=pending` and
stop before successor authorization; the pending design marker is not a
substitute. This current predecessor design records that gate as deferred until
post-integration and does not treat the absent post-integration artifact as a
local implementation input.

### Required repository contracts

- `README.md`, `agents/README.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/canonical/CLI_ENTRYPOINTS.md`, `agents/canonical/CODEX_SUBAGENTS.md`.
- `documents/README.md`, `tools/README.md`, and `documents/tools/README.md` for canonical reader-facing entrypoints and public graph routing.
- `documents/SHARED_RUNTIME_SURFACES.md`, `documents/shared-runtime-surfaces.toml`, `documents/repo-structure-contract.toml`.
- `documents/structured-analysis/graph-dsl.md`, `documents/structured-analysis/database-design.md`, `documents/structured-analysis/dependency-header-analysis.md`.
- `documents/dependency-manifest-design.md`, `documents/semantic_index.md`, `documents/search-coordination.md`, `documents/responsibility-scope-management.md`.
- `documents/tools/check_design_doc_claims.md`, `documents/tools/render_dependency_manifest_graph.md`, `tools/catalog.yaml`, and `agents/skills/catalog.yaml`.
- `rust/agent-canon/Cargo.toml` and `rust/agent-canon/Cargo.lock` for the no-new-dependency inventory; no Python or shell dependency manifest is changed.

### Required source paths and symbols

- `rust/agent-canon/src/main.rs`: `fn main`, `let args: Vec<String> =
  env::args().collect()`, the current repeated literal `if args.len() >= 2 &&
  args[1] == <command>` arms, each `run(&args[2..])` call, module declarations,
  dependency-manifest arm, and usage string. Preserve that manual form and add
  only the exact graph module/arm defined above.
- `rust/agent-canon/src/graph.rs`: new one-unit controller, store adapter, exact public operation implementations, and `GraphIntegrationRecord` persistence/verification; before creating it, read the design naming/signature rows and the existing adapter sources. There is no existing file to read.
- `rust/agent-canon/src/dependency_manifest.rs`: all current types in the reuse
  table, `ManifestParser`, `scan_manifest_lines`,
  `SnapshotRequest {root,profile,output_jsonl}`, private
  `SnapshotHeader.profile`, `capture_snapshot`, `write_snapshot_jsonl`,
  `parse_snapshot_args`'s current `profile == "parent"` rule,
  `contains_manifest_marker`, `write_atomic_with_failure`,
  `AtomicFailurePoint`, `CandidateCleanup`, and the exact deletion region for
  normalized transport. Expose only `write_snapshot_jsonl` and the narrow
  snapshot-profile accessor; graph maps public `default` to producer `parent`.
- `rust/agent-canon/src/structured_analysis.rs`: `run`, `run_build`, `run_graph_contract`, `build_structured_analysis_cache`, `collect_documents`, `collect_files`, `initialize_graph_schema`, `has_dependency_manifest`, `dependency_manifest_values`, `dependency_coverage_rules`, Graph DSL schema/materialization, and validator; remove the three dependency functions and header bounds, then add the exact `validate_graph_connection` adapter signature from this brief.
- `rust/agent-canon/src/semantic_index.rs`: `ContextPackArgs`, `ContextCell`, `context_pack`, `init_schema`, `open_cache_connection`, and `files`/`nodes`/`embeddings` schema.
- `tools/agent_tools/generate_agent_runtime_dashboard.py`: `AgentRuntimeDashboard`, `RuntimeDashboardSummary`, `HookWorkflowBreakdownReader`, `TokenUsageBreakdownReader`, `SelectionMetricsReader`, `read_candidate_selection_resets`, `selection_source_path_candidates`, `render_dashboard_api`, and existing `agent_runtime_dashboard.v1` fields; `tools/agent_tools/compare_codex_token_footprints.py::{TokenFootprint,parse_token_usage}` and `tools/agent_tools/workflow_monitor.py::append_monitoring`; read the current event/report producers before adding the typed path rejection and measurement projections.
- `.codex/hooks/skill_usage_logger.py::append_skill_usage_entry`, `.codex/hooks/hook_event_log.py::HookLogContext.append`, and `tools/agent_tools/runtime_log_paths.py::hook_results_dir`; read the current `WORKFLOW_FIELDS`, `hook_log_namespace`, `candidate_workflows`, selected-workflow fields, and canonical JSONL path resolver before changing attribution ownership.
- `tools/agent_tools/check_design_doc_claims.py`: `GraphClaimConsumer.check_document`, `ClaimTokenClass`, `Claim`, `Finding`, `CheckResult`, `build_parser`, and the exact graph-integration prerequisite; read `resolve_claim_token_path`, `parse_manifest_edges`, and `dependency_closure` only to delete/replace them, never to reuse them.
- `tools/agent_tools/graph_client.py`: new consumer-only `GraphClient`,
  `GraphClientError`, `GraphResponse`, `GraphDependencyFact`, and the exact
  `invoke`/`status`/`context`/`query`/`dependency_facts` interfaces in this
  brief; read the public CLI schemas before creating it.
- `tools/agent_tools/dependency_manifest_records.py` and `bind_r2_scope.py`: read to identify and delete all duplicate routes; do not copy their transport design.
- `tools/agent_tools/search.py`: current `SearchCorpus.dependency_edges`,
  `load_corpus`, `header_dependency_hits`, provider selection, existing
  `AGENT_SEARCH` output, and the direct
  `vector_search.parse_dependency_edges(request.root, documents)` call; replace
  only that manifest-fact route with the one graph query defined above.
- `tools/agent_tools/vector_search.py`: `DependencyEdge`,
  `parse_dependency_edges`, `build_context_expansion`, and dependency frontier
  helpers; remove manifest ownership while retaining text/TF-IDF and Python
  symbol/call facts.
- `tools/agent_tools/search_index.py`: `responsibility_from_text` and its `vector_search.strip_manifest_line` call; remove the call and read graph owner/dependency projections downstream of build.
- `tools/agent_tools/tool_catalog.py`: `Finding`, `CatalogRow`, `CatalogReport`,
  `load_catalog`, `validate_catalog`, and catalog relation rendering; remove
  `HEADER_SCAN_LINES`/`has_dependency_manifest`, retain YAML/catalog/public-row
  validation as the graph-build producer, and token-parse only the fixed
  manual-dispatch inputs under the exact grammar above; never call the graph.
- `tools/agent_tools/render_dependency_manifest_graph.py`, `check_dependency_header_format.sh`, `check_dependency_graph.sh`, `scan_dependency_headers.sh`, `run_repo_dependency_review.sh`, and `scan_code_dependencies.sh`: current graph/checker orchestration and output contracts.
- `tools/agent_tools/tool_drift.py`: read and disposition every current symbol
  `ManifestEdge`, `has_dependency_manifest`, `strip_manifest_line`,
  `repo_relative`, `normalize_target`, `manifest_edges`, `HEADER_SCAN_LINES`,
  `MANIFEST_FIELD_COUNT`, and `MANIFEST_REASON_MAX_SPLIT`, plus the `os` import;
  delete them, retain
  the link/text/catalog policy symbols named above, and replace only the edge
  source with `GraphResponse.dependency_facts`.
- `tools/agent_tools/prose_reasoning_graph.py`: preserve prose-DSL parsing but
  remove dependency-header parsing and use canonical graph evidence.
- `tools/agent_tools/agent_team.py`, `tools/agent_tools/bootstrap_agent_run.py`, `tools/agent_tools/task_start.py`, and `tools/agent_tools/waterfall_gate_check.py`: four read-only branch-composition inspection surfaces; do not edit or integrate them into this graph unit. `agents/agents_config.json` is separate from those four helpers and is an explicitly allowed graph-route config surface in the file plan. The broader file plan separately authorizes graph-route edits in its explicitly listed CLI, workflow, skill, catalog, documentation, producer, consumer, and dependency-manifest owners. Any other header is out of scope and must not be invented by the worker.
- `tools/agent_tools/check_dependency_headers.py`: current `build_parser`,
  `changed_paths`, `should_check`, parser/registry symbols, result labels, and
  tests; apply the exact status/context mapping above. Also read
  `tools/agent_tools/import_responsibility.py`, `responsibility_scope.py`,
  `check_dependency_graph.sh`, `scan_dependency_headers.sh`, and
  `scan_code_dependencies.sh` at their producer/consumer boundaries.
- `tools/agent_tools/repo_structure_contract.py`: structure contract output and canonical/view/generated/submodule boundary producer.
- `tools/agent_tools/tool_catalog.py`: `Finding`, `CatalogRow`, `CatalogReport`, `load_catalog`, and `validate_catalog`; convert header presence out of this producer, retain catalog/public output as a graph-build input, and never make it a graph consumer. Its replacement contract is YAML existence plus mapping/enum/public-row validation; dependency-header coverage is not a catalog finding.
- `agents/skills/dependency-analysis.md`, `agents/skills/prose-reasoning-graph.md`, `.agents/skills/prose-reasoning-graph/SKILL.md`, and `.codex/config.toml`: prompt/config boundaries; graph adds no MCP/config route.
- Exact dependency-header edit set: `rust/agent-canon/src/graph.rs`, `rust/agent-canon/src/main.rs`, `rust/agent-canon/src/dependency_manifest.rs`, `rust/agent-canon/src/structured_analysis.rs`, `rust/agent-canon/src/semantic_index.rs`, `tools/agent_tools/graph_client.py`, `tools/agent_tools/check_design_doc_claims.py`, `tools/agent_tools/search.py`, `tools/agent_tools/vector_search.py`, `tools/agent_tools/search_index.py`, `tools/agent_tools/tool_catalog.py`, `tools/agent_tools/tool_drift.py`, `tools/agent_tools/prose_reasoning_graph.py`, `tools/agent_tools/dependency_manifest_records.py`, `tools/agent_tools/bind_r2_scope.py`, `tools/agent_tools/render_dependency_manifest_graph.py`, `tools/agent_tools/check_dependency_headers.py`, `tools/agent_tools/check_dependency_header_format.sh`, `tools/agent_tools/check_dependency_graph.sh`, `tools/agent_tools/scan_dependency_headers.sh`, `tools/agent_tools/run_repo_dependency_review.sh`, `tools/agent_tools/scan_code_dependencies.sh`, `tools/agent_tools/import_responsibility.py`, `tools/agent_tools/responsibility_scope.py`, `tests/agent_tools/test_search.py`, `tests/agent_tools/test_tool_drift.py`, `tests/agent_tools/test_check_dependency_headers.py`, `tests/agent_tools/test_tool_catalog.py`, `tests/fixtures/tool_catalog/main_manual_dispatch.rs`, `tests/fixtures/tool_catalog/graph_manual_dispatch.rs`, `documents/tools/check_design_doc_claims.md`, `documents/tools/render_dependency_manifest_graph.md`, `documents/dependency-manifest-design.md`, `documents/structured-analysis/dependency-header-analysis.md`, `documents/structured-analysis/graph-dsl.md`, `agents/canonical/CLI_ENTRYPOINTS.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/workflows/implementation-waterfall-workflow.md`, `agents/agents_config.json`, `agents/skills/dependency-analysis.md`, `agents/skills/prose-reasoning-graph.md`, `.agents/skills/prose-reasoning-graph/SKILL.md`, `README.md`, `agents/README.md`, `documents/README.md`, `tools/README.md`, `documents/tools/README.md`, `tools/catalog.yaml`, and `agents/skills/catalog.yaml`. The new `search.py` upstream header names `graph_client.py` for dependency facts and narrows `vector_search.py` to text/Python facts; `test_search.py`, `tool_drift.py`, `test_tool_drift.py`, `check_dependency_headers.py`, `test_check_dependency_headers.py`, `tool_catalog.py`, `test_tool_catalog.py`, and both manual-dispatch fixtures receive matching graph/producer/test edges. The four inspection-only helpers named in the Branch composition rule are deliberately excluded because neither their implementation nor their header changes are in this unit. Any other header is out of scope and must not be invented by the worker.
- Exact dependency-header semantics for findings 1–5: `main.rs` adds
  `downstream implementation graph.rs` and `graph.rs` points upstream to
  `dependency_manifest.rs`, `structured_analysis.rs`, and `semantic_index.rs`;
  `search.py` adds `upstream implementation ./graph_client.py provides
  canonical dependency query facts` and rewrites its `vector_search.py` edge
  to text/TF-IDF and Python code facts only; `test_search.py` adds the matching
  graph-client/query-test edge. `check_dependency_headers.py` adds
  `upstream implementation ./graph_client.py provides verified manifest
  context` and keeps the contract-registry document only as design provenance,
  not a decoder input; its test adds the matching consumer-adapter edge.
  `tool_drift.py` adds `upstream implementation ./graph_client.py provides
  canonical dependency query facts`, and `test_tool_drift.py` adds that adapter
  plus checker edge. `tool_catalog.py` adds upstream implementation edges to
  `main.rs` and `graph.rs` as fixed extractor inputs; `test_tool_catalog.py`
  points to the two fixtures. Each fixture has `contract test`, responsibility,
  an upstream design edge to this brief, and a downstream implementation edge
  to `test_tool_catalog.py`; no fixture is header-exempt.
- Runtime-evidence dependency/header expansion: include `tools/agent_tools/generate_agent_runtime_dashboard.py`, `tools/agent_tools/compare_codex_token_footprints.py`, `tools/agent_tools/workflow_monitor.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/hook_event_log.py`, `tools/agent_tools/runtime_log_paths.py`, their owning tool docs/skills, `tests/agent_tools/test_generate_agent_runtime_dashboard.py`, `tests/agent_tools/test_compare_codex_token_footprints.py`, and the applicable hook tests in the same graph/runtime unit. Their dependency edges remain producer-owned; graph adds only captured provenance/context projections.
- `tests/agent_tools/test_dependency_manifest_tools.py`,
  `test_check_design_doc_claims.py`, `test_check_dependency_headers.py`,
  `test_search.py`, `test_tool_drift.py`,
  `test_generate_agent_runtime_dashboard.py`,
  `test_compare_codex_token_footprints.py`, `test_tool_catalog.py`,
  `test_agent_team_templates.py`, `test_task_start_and_close.py`,
  `test_waterfall_gate_check.py`, and every fixture named in `KG-TEST-LAST`;
  runtime-result directories are read-only evidence, not test write targets.

### Required reviews and commands

- Read `agents/workflows/implementation-waterfall-workflow.md` gates for design approval, source mechanism, consumer integration, and closeout.
- Read the fresh same-SHA review outputs at the exact paths `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_review.md` and `reports/agents/20260712-090608-context-packettool-skill-routing/graph_document_flow_review.md` before implementation; the existing bytes at those paths are historical context only, and a fresh `revise` decision returns to this brief.
- Treat `Validation mapping and exact oracles` items 1–31 above as the normative implementation validation/test plan. `test_design=inactive` means no separate `test_plan.md` is created; activate the repository `test-design` route only if implementation leaves an unresolved oracle after the source mechanism exists.
- Before any successor handoff, verify the canonical archived predecessor record with `python3 tools/agent_tools/github_publish.py verify-predecessor-integration --record <explicit-record> --archive-manifest <same-snapshot>/archive_manifest.json --expected-unit-id knowledge_graph`; missing/unverified record is `successor_predecessor_gate=pending` and blocks successor authorization. The current predecessor design does not run this post-integration command before its same-SHA review gate.
- Run `python3 tools/agent_tools/check_convention_compliance.py` for the affected graph/source PR.
- Run `tools/bin/agent-canon docs check <changed-doc-paths>` after doc edits.
- Run `python3 vendor/agent-canon/tools/agent_tools/repo_structure_contract.py --root . --contract vendor/agent-canon/documents/repo-structure-contract.toml --format text` and `python3 vendor/agent-canon/tools/agent_tools/responsibility_scope.py --root . --format text`, with `cwd=<parent-root>`.
- Run the canonical Rust build/test/check route for `rust/agent-canon`, then graph source/parser tests before consumer tests.
- Run `agent-canon graph build --root <parent-root> --profile default --format json`, `agent-canon graph status --root <parent-root> --profile default --format json`, `agent-canon graph query --root <parent-root> --profile default --path <known-path> --format json`, and `agent-canon graph context --root <parent-root> --profile default --path <design-path> --token <known-token> --format json`; separately require `--profile parent` to fail with usage exit `2`.
- Run the canonical runtime producer with `python3 <parent-root>/vendor/agent-canon/tools/agent_tools/generate_agent_runtime_dashboard.py --root <parent-root> --out <temp>/runtime-dashboard.md --api-out <temp>/runtime-dashboard.json`, inspect its typed path diagnostics, workflow-attribution count, token comparison count, and all `RuntimeMeasurement` fields, then feed that captured API artifact through the graph build; do not read raw runtime logs from a graph consumer.
- Run `bash tools/agent_tools/run_repo_dependency_review.sh` after dependency edges change and verify no second parser/fact authority remains.

## Design Side-Effect Map

Each decision names the affected implementation, document, workflow,
prompt/config, validation, dependency-manifest, and user-facing surfaces. The
same row is the owner/review/validation join used by the implementation trace.

| Map ID / decision | Implementation | Document | Workflow / prompt / config | Validation or test-plan item | Dependency-manifest surface | User-facing surface | Owner stage | Review gate | Clause | Reuse precedent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SEM-01` One parser/full-file scan | `dependency_manifest.rs`, graph adapters, checker wrappers | dependency-manifest and adapter docs | workflow commands call graph; no new config key | line-80 regression and all-consumer parity; no `test_plan.md` | `ManifestParser`, header scanners, graph edge producer | operator sees one graph route | `KG-SRC` | design + source | `KG-4` | `ManifestParser`, `dependency-manifest-design.md` |
| `SEM-02` Parent-owned DB | `graph.rs`, fixed path resolver, parent root integration | shared-surface and CLI docs | `.codex/config.toml` is unchanged; no MCP/config state | no DB under AgentCanon; fixed parent path | source snapshot records carry parent root | parent owns generated state | `KG-SRC` | source + parent integration | `KG-2`, `KG-3` | `SHARED_RUNTIME_SURFACES.md`, Graph DSL SQLite materialization |
| `SEM-03` Graph DSL storage | graph store adapter and structured-analysis bridge | Graph DSL/database docs | skill prompt names Graph DSL as authority | `graph-contract` validates core tables | dependency adapter maps to `nodes`/`edges` | stable graph query JSON | `KG-SRC` | Graph DSL contract | `KG-5` | `structured_analysis.rs::run_graph_contract` |
| `SEM-04` Producer-owned `D`/`R` | import/scope/code/semantic-index adapters | dependency-header analysis and search docs | task packets route to producers, not graph inference | producer/source/owner evidence on every explicit edge | `D` from manifest, `R` from authoritative tools | exact provenance shown in query/context | `KG-SRC` | dependency/source | `KG-4`, `KG-8` | `ImportRecord`, `ScopeIndex`, `ContextCell` |
| `SEM-05` Explicit unresolved/ambiguous sets | diagnostics and status/query/context projection | graph completeness contract | skill wording preserves unresolved leaves | missing/multi-candidate fixtures remain visible; no post-implementation test-design activation yet | stale/broken targets remain diagnostics | status explains incomplete evidence | `KG-SRC` | mathematical/design | `KG-6` | `SourceUniverse`, Graph DSL diagnostics |
| `SEM-06` Atomic/freshness lifecycle | candidate writer, validator, publisher | CLI/lifecycle docs | no implicit rebuild prompt or config fallback | failure leaves prior DB; changed inputs are stale | producer artifact hashes drive freshness | status is deterministic | `KG-SRC` | lifecycle | `KG-7` | `dependency_manifest.rs::write_atomic_with_failure`, `AtomicFailurePoint`, `CandidateCleanup` |
| `SEM-07` Graph-backed claim checker | `graph_client.py`, `check_design_doc_claims.py`, `vector_search.py` | checker/search docs | checker skill route calls graph context | path/evidence/math token cases use graph only | checker no longer parses headers | exact owner/source/dependency context | `KG-CONSUME` | consumer/API | `BR-2`, `KG-7` | `ClaimTokenClass`, `CheckResult` |
| `SEM-08` Remove R2 transport/binder | Rust/Python deletion and catalog cleanup | workflow/skill/catalog docs | remove R2/binder prompts and route entries | replacement source checks precede matrix deletion | no normalized-record or binder edge | no historical R2 command | `KG-TEST-LAST` | deletion/PR | `KG-3`, `BR-1`, `BR-3` | dead-code evidence; Graph DSL boundary |
| `SEM-09` One graph CLI | `main.rs`, new graph module, parent wrapper, `tool_catalog.py` | CLI/tool index docs | `agent-canon graph ...` is the only public graph prompt/route | exact manual-main and four-arm graph fixtures; help/smoke; `default -> parent` request/fingerprint cases | one `tool_catalog.py` artifact is captured once; `structure-catalog` owns `catalog` rows and `public-surface` owns token-parsed `public` rows; source-snapshot records both profiles | one generic operator entrypoint | `KG-CONSUME` | API/document-flow | `KG-1`, `KG-3` | current repeated `main.rs` `if` dispatch, `structured_analysis::run`, `SnapshotRequest`, `CatalogReport`, `PublicSurfaceReport` |
| `SEM-10` Direct coordinated search consumer | `graph_client.py`, `search.py::{SearchCorpus,load_corpus,header_dependency_hits}`, `search_index.py`, `vector_search.py` | search-coordination and semantic-index docs | only selected `header-deps` performs one all-dependency query; other providers make no graph call | graph-client spy, evidence provenance, non-fresh/no-fallback, and direct-parser residual | `search.py` header changes from vector manifest facts to `graph_client.py`; `vector_search.py` retains text/Python facts | exact graph-backed source/target candidates | `KG-CONSUME` | consumer/dependency | `KG-4`, `KG-5`, `KG-8` | `ProviderHit`, `Candidate`, `ContextCell`, current scoring/output |
| `SEM-10` Dependency-check consumers | `check_dependency_headers.py`, `check_dependency_header_format.sh`, `check_dependency_graph.sh`, `scan_dependency_headers.sh`, `run_repo_dependency_review.sh` | dependency-header and review docs | Python checker performs exact status plus per-path context arrays; shells use fixed-CWD graph operations | present/contract/responsibility mapping, verified profile pair, non-fresh/no-fallback, parser-symbol residual | checker/test headers add `graph_client.py`; producer owns registry and source spans | existing `DEPENDENCY_HEADERS` result with typed graph evidence | `KG-CONSUME` | consumer/dependency | `KG-4`, `KG-8` | `build_parser`, `changed_paths`, `should_check`, current output labels, `GraphClient` |
| `SEM-10` Render/drift/prose consumers | `render_dependency_manifest_graph.py`, symbol-complete `tool_drift.py`, `prose_reasoning_graph.py` | render, tool-drift, and prose-graph docs | graph query/context is the only dependency/owner evidence input | drift parity, one-query/non-fresh cases, and exact nine-symbol-plus-import residual | `tool_drift.py` deletes `ManifestEdge`, three constants, five parser/normalizer functions including `repo_relative`, and the now-unused `os` import; test/header edges add `graph_client.py` | rendered/drift/prose edges retain producer/evidence refs | `KG-CONSUME` | consumer/dependency | `KG-5`, `KG-8` | retained `ToolContract`/`Finding`/link policy, render records, `ContextCell` |
| `SEM-11` Runtime evidence/dashboard repair | `generate_agent_runtime_dashboard.py`, `compare_codex_token_footprints.py`, `workflow_monitor.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/hook_event_log.py`, `runtime_log_paths.py`, graph runtime adapter/context projection | runtime dashboard docs, log-analysis skill, workflow-monitoring contract, hook-event contract, generated runtime views | canonical dashboard/token/hook producers remain the only logger/schema owners; graph consumes captured API output | typed malformed-path rejection; measured zero-versus-missing tokens; exact `HookLogContext.append`/`append_skill_usage_entry` attribution owner; all `RuntimeMeasurement` fields; no raw-log reparse | producer artifacts, exact diagnostic codes, source-byte/hash provenance, and context measurements | `KG-SRC` then `KG-CONSUME` | source/runtime + evidence | `RT-1/2/3` | `AgentRuntimeDashboard`, `HookWorkflowBreakdownReader`, `TokenUsageBreakdownReader`, `TokenFootprint`, `MonitoringEntries`, `append_monitoring` |
| `SEM-09` Root/docs/generated surfaces | `README.md`, `agents/README.md`, `documents/README.md`, `tools/README.md`, `documents/tools/README.md`, CLI/workflow docs, `tools/catalog.yaml`, `agents/skills/catalog.yaml`, generated/root views | public CLI and shared-runtime docs | only `agent-canon graph ...`; no MCP or private route | docs/convention/public-surface/dependency-header checks | one public graph route and parent DB ownership | `KG-CONSUME` | API/document-flow | `KG-1`, `KG-2`, `KG-3`, `KG-9` | existing reader maps, catalogs, root-view contract |
| `SEM-08` Dirty/stale fixture surfaces | dirty tests/fixtures plus normalized/binder matrices and decoder tests | deletion and migration docs | preserve user-owned dirty semantics, then delete obsolete matrices after source pass | source-first residual/deletion scan | no normalized/binder manifest edge | no historical R2 command or fixture route | `KG-TEST-LAST` | deletion/PR | `BR-1`, `BR-3`, `KG-9` | current fixture harness and dirty cases |

## Design-To-Implementation Trace

| Map ID | Planned edit | Design section | Clause | Reuse precedent | Validation |
| --- | --- | --- | --- | --- | --- |
| `SEM-02`, `SEM-03` | Add `graph.rs` controller and Graph DSL adapter | Source and store mechanism; naming plan | `KG-1`, `KG-2`, `KG-5`, `KG-6`, `KG-7` | `structured_analysis.rs` schema/checker, `semantic_index.rs` context store | Rust compile/unit checks; graph build/status/query/context smoke |
| `SEM-09`, `SEM-08` | Add `mod graph;` and the exact manual `if args.len()...graph::run(&args[2..])` arm, four literal graph-module arms, token-parsed public rows, and retire the public dependency-manifest route | Public CLI; producer authority; deletion list | `KG-1`, `KG-3`, `BR-3` | current `main.rs` repeated dispatch, `structured_analysis::run`, `CatalogReport` | two positive dispatch fixtures, generated negative mutations, exact spans, CLI help/unknown-route checks |
| `SEM-01`, `SEM-04` | Simplify `dependency_manifest.rs` and remove line cap/transport | Mathematical contract; source mechanism | `KG-4`, `KG-8` | `ManifestParser`, `capture_snapshot`, `SourceUniverse` | complete-file parser and producer provenance checks |
| `SEM-03`, `SEM-04` | Expose narrow structured-analysis/semantic-index adapters and remove structured-analysis dependency extraction | Canonical-surface relationships; storage contract | `KG-5`, `KG-8` | `run_graph_contract`, `ContextCell`, existing schemas | Graph DSL validation, full-file source parity, and exact context evidence |
| `SEM-01`, `SEM-04`, `SEM-07`, `SEM-10` | Add `graph_client.py`/`GraphDependencyFact`; convert dependency/search/graph render tools, including `search.py`'s direct `vector_search.parse_dependency_edges` call, to consumers | Consumers and public edges; claim decision | `KG-4`, `KG-5`, `KG-8` | current producer reports, `ProviderHit`/`Candidate`, and vector-search text/Python records | one exact all-dependency query when selected; no graph call otherwise; provenance and non-fresh/no-fallback oracles |
| `SEM-07` | Convert `check_design_doc_claims.py` | Claim checker decision | `BR-2`, `KG-7` | `ClaimTokenClass`, `CheckResult`, existing output format | path-relative and graph-evidence fixtures |
| `SEM-08`, `SEM-09` | Update docs, skills, catalog, and dependency headers | Consumers/docs/skills | `KG-1`, `KG-3`, `KG-9`, `BR-3` | existing CLI/catalog/dependency-header contracts | Markdown, convention, dependency review |
| `SEM-05`, `SEM-08` | Port dirty semantic cases, then delete R2 matrices/binder/decoder tests | Dirty/stale tests and deletion list | `BR-1`, `BR-2`, `KG-9` | existing test harness and fixture style | source mechanism first; public regression/property only if missing |
| `SEM-06` | Implement `default -> SnapshotRequest.profile=parent`, canonical profile fingerprinting/verification, candidate validation, rename, and durability boundary | Freshness and atomic publication contract | `KG-7` | current `SnapshotRequest`, `capture_snapshot`, private `SnapshotHeader.profile`, `write_snapshot_jsonl`, atomic writer/failure seams | omitted/explicit-default equivalence, public-parent usage failure, captured request/path, profile mismatch refusal, atomic/freshness transitions |
| `SEM-10` | Remove `search_index.py` manifest-line owner extraction and `search.py::load_corpus`'s direct dependency parser call | Search consumer boundary | `KG-4`, `KG-5`, `KG-8` | `ContextCell`, coordinated-search scoring/output, graph context/query JSON | search/index parity, one-query provider spy, exact provenance, non-fresh refusal, parser-symbol residual scan |
| `SEM-11` | Repair canonical runtime dashboard path rejection, workflow attribution, token measurement ingestion, and context measurement projection | Runtime evidence producer and repair contract | `RT-1/2/3`, `KG-7`, `KG-9` | `AgentRuntimeDashboard`, `HookWorkflowBreakdownReader`, `TokenUsageBreakdownReader`, `TokenFootprint`, `MonitoringEntries`, `append_monitoring`, `append_skill_usage_entry`, `HookLogContext.append` | hook/dashboard source tests first; graph runtime projection/diagnostic checks; no duplicate logger/schema |
| `SEM-01` | Modify `tools/agent_tools/scan_code_dependencies.sh` to accept the exact `--paths-file` input and emit the required completion marker; no internal path enumeration remains on the graph route | Scanner and source-universe contract | `KG-4`, `KG-8` | existing shell scanner, `P_scan`, producer TSV contract | nonempty/empty/missing/malformed paths-file and marker checks |
| `SEM-10` | Convert `check_dependency_headers.py`, `check_dependency_header_format.sh`, `check_dependency_graph.sh`, `scan_dependency_headers.sh`, and `render_dependency_manifest_graph.py` to graph consumers | Consumer boundary and deletion list | `KG-4`, `KG-5`, `KG-8` | checker selection/output formats, `GraphClient`, manifest context items | exact Python status/per-path-context arrays and result mapping; fixed-CWD shells; no tokenizer/target normalizer |
| `SEM-10` | Delete `tool_drift.py::{ManifestEdge,HEADER_SCAN_LINES,MANIFEST_FIELD_COUNT,MANIFEST_REASON_MAX_SPLIT,has_dependency_manifest,strip_manifest_line,repo_relative,normalize_target,manifest_edges}` and its now-unused `os` import, remove only its catalog header oracle, and feed retained drift policy from `GraphDependencyFact`; convert prose dependency context likewise | Search/context consumer boundary | `KG-5`, `KG-8` | retained drift link/reverse/catalog finding logic, prose result records, `ContextCell` | canonical fact parity, missing-link/reverse/kind cases, non-fresh failure, exact symbol/import residual scan |
| `SEM-08`, `SEM-09` | Update `README`/CLI entrypoints, `tools/catalog.yaml`, `agents/skills/catalog.yaml`, graph skill/docs, dependency headers, and generated/root views; remove old route mentions | Consumers/docs/skills and public-surface producer | `KG-1`, `KG-3`, `KG-9`, `BR-3` | existing catalog, shared-root view, dependency-header contracts | docs/convention/dependency checks and public-surface span reproducibility |
| `SEM-08` | Remove `dependency_manifest_records.py`, `bind_r2_scope.py`, normalized/binder fixtures, duplicate matrices, and their stale tests after source mechanism checks | Explicit deletion list and dirty-path disposition | `BR-1`, `BR-3`, `KG-3`, `KG-9` | existing fixture harness; ported dirty cases | deletion residual scans and source-first closeout evidence |

### Trace-to-current-clause join

| Trace Map ID | Direct current-clause IDs |
| --- | --- |
| `SEM-02`, `SEM-03` | `KG-A`, `KG-B`, `KG-C`, `KG-C1`, `KG-C2`, `KG-C3`, `KG-C9`, `SEARCH-1`, `SEARCH-2`, `SEARCH-6` |
| `SEM-09`, `SEM-08` | `KG-A`, `KG-G`, `KG-H`, `KG-I`, `KG-C8`, `KG-C9`, `KG-C10`, `SEARCH-6`, `SEARCH-7` |
| `SEM-01`, `SEM-04` | `KG-C`, `KG-E`, `KG-F`, `KG-C3`, `KG-C4`, `KG-C7`, `SEARCH-1`, `SEARCH-2`, `SEARCH-3`, `SEARCH-4`, `SEARCH-5` |
| `SEM-03`, `SEM-04` | `KG-B`, `KG-C`, `KG-E`, `KG-F`, `KG-C3`, `KG-C6`, `SEARCH-1`, `SEARCH-4` |
| `SEM-01`, `SEM-04`, `SEM-07`, `SEM-10` | `KG-C`, `KG-F`, `KG-I`, `KG-C3`, `KG-C4`, `KG-C6`, `KG-C7`, `SEARCH-3`, `SEARCH-4`, `SEARCH-5`, `SEARCH-8` |
| `SEM-07` | `KG-H`, `KG-I`, `KG-C6`, `KG-C9`, `SEARCH-4`, `SEARCH-5`, `SEARCH-8` |
| `SEM-08`, `SEM-09` | `KG-A`, `KG-B`, `KG-G`, `KG-H`, `KG-I`, `KG-C8`, `KG-C9`, `KG-C10`, `SEARCH-6`, `SEARCH-7` |
| `SEM-05`, `SEM-08` | `KG-G`, `KG-I`, `KG-J`, `KG-C4`, `KG-C7`, `KG-C8`, `KG-C10`, `SEARCH-5`, `SEARCH-7`, `SEARCH-8` |
| `SEM-06` | `KG-D`, `KG-J`, `KG-C1`, `KG-C2`, `KG-C5`, `KG-C10`, `SEARCH-4`, `SEARCH-7` |
| `SEM-10` | `KG-C`, `KG-F`, `KG-I`, `KG-C3`, `KG-C4`, `KG-C6`, `KG-C7`, `SEARCH-3`, `SEARCH-4`, `SEARCH-8` |

### Search-packet disposition ledger

The source packet names negative (`N*`) and coverage (`C*`) checks for every
preserved search clause, plus packet IDs `F6`–`F10`. They are not unowned
requirements: this table is the authoritative disposition in the Side-Effect
Map and Trace. `N*` means the prohibited route is absent; `C*` means the
positive evidence fields are present.

| Packet IDs | finding_class | evidence_cells | route_target | instance_partition | required_packet | closeout_gate | Side-Effect Map | Trace | Validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SEARCH-1-N*`, `SEARCH-1-C*` | `structure_boundary` | root/view/submodule mapping; structure status | structure owner when a contradiction exists | `path_scope` | structure evidence + canonical/view boundary + source-universe decision | structure contract or typed structure issue | `SEM-02`, `SEM-09` | `SEM-02`, `SEM-09` | 1, 3, 19 |
| `SEARCH-2-N*`, `SEARCH-2-C*` | `owner_identification` | responsibility-scope status; owner/source spans | responsibility owner | `owner_scope` | owner map + replaceable unit + downstream impact | owner boundary and scope evidence | `SEM-04` | `SEM-01`, `SEM-04` | 4, 20 |
| `SEARCH-3-N*`, `SEARCH-3-C*` | `query_plan` | relation family; universe; reuse target; expected signal | query/graph owner | `relation_family` | query-plan row + stop condition + next decision | reproducible query row or typed gap | `SEM-03`, `SEM-10` | `SEM-03`, `SEM-10` | 6, 20 |
| `SEARCH-4-N*`, `SEARCH-4-C*` | `evidence_promotion` | producer; authority; freshness; impact; bounded context | graph context/semantic-index owner | `evidence_cell` | selected fact + provenance + local artifact reference | exact evidence or typed unresolved/ambiguous result | `SEM-04`, `SEM-05`, `SEM-07` | `SEM-04`, `SEM-07` | 4, 9, 10 |
| `SEARCH-5-N*`, `SEARCH-5-C*` | `research_escalation` | stale/missing/schema/owner/coverage/unsupported/conflict status | owning producer or planning gate | `finding_partition` | typed trigger + owner + required packet | re-search result or explicit escalation | `SEM-05`, `SEM-06` | `SEM-05`, `SEM-06` | 7, 8, 9, 21 |
| `SEARCH-6-N*`, `SEARCH-6-C*` | `canonical_routing` | canonical command; active/deferred/private route | AgentCanon canonical owner | `route_surface` | canonical source path + route decision | canonical route evidence; private route absent | `SEM-02`, `SEM-08`, `SEM-09` | `SEM-08`, `SEM-09` | 12, 13, 16, 17 |
| `SEARCH-7-N*`, `SEARCH-7-C*` | `recurrence_prevention` | evidence cell; owner; partition; packet; gate | log/finding owner | `finding_partition` | finding packet + recurrence owner + closeout gate | finding closure or typed deferral | `SEM-05`, `SEM-06`, `SEM-08` | `SEM-05`, `SEM-06`, `SEM-08` | 7, 9, 17 |
| `SEARCH-8-N*`, `SEARCH-8-C*` | `bounded_context` | facts; provenance; unresolved/ambiguous/excluded counts; validation | graph context owner | `query_scope` | bounded context + validation + deferred-risk fields | no stale claim promotion | `SEM-05`, `SEM-07`, `SEM-10` | `SEM-07`, `SEM-10` | 9, 10, 20 |
| `F6` | `graph_population` | source manifest; `U/D/O/G/X/A`; provenance; normalized facts | Graph DSL/structured-analysis + dependency/responsibility/import owners | `parent_root|relation_family` | build manifest + extractor provenance + logical-identity map + failing finite-set assertion | two-build normalized equality + lossless projection/reconciliation | `SEM-01`, `SEM-04` | `SEM-01`, `SEM-04` | 2, 3, 4 |
| `F7` | `graph_freshness` | HEAD; dirty state; content hash; pin; schema/tool fingerprints; status | graph build/freshness owner | `parent_root|source_change_kind` | before/after manifest + add/modify/delete fixture + atomic result | fresh/stale/missing/schema-mismatch/build-failed matrix and no-silent-rebuild evidence | `SEM-06` | `SEM-06` | 7, 8, 19 |
| `F8` | `graph_coverage` | `V(G)=normalize(U\\X)`; `O\\D`; `D\\O`; uncovered/ambiguous/excluded counts | coverage checker + dependency/responsibility/import reviewers | `relation_family` | declared universe + comparable family + reconciliation findings + X/A reasons | finite-set equality/subset checks or visible typed escalation | `SEM-05` | `SEM-05` | 3, 9, 21 |
| `F9` | `graph_query` | relation-family query matrix; provenance; freshness/status; bounded context cells | semantic-index/query + unified CLI owners | `relation_family|query_scope` | query plan row + status evidence + selected facts + local artifact reference | reproducible family queries and no stale claim promotion | `SEM-03`, `SEM-07`, `SEM-10` | `SEM-03`, `SEM-07`, `SEM-10` | 6, 10, 20 |
| `F10` | `graph_proof_boundary` | finite-set oracle; adversarial/property fixture; formal-rule selection | validation owner; formal-proof owner only for nontrivial rules | `normalization|projection|closure` | trusted extraction assumption + executable oracle + proof target/non-target | no parser/source semantic-completeness claim; defer unnecessary proof | `SEM-05`, `SEM-08` | `SEM-05`, `SEM-08` | 17, 18, 21 |

`test_design=inactive`: the owning mechanism, existing Graph DSL checker,
canonical dashboard/token producers, and targeted fixture oracles are sufficient. If implementation
review finds an unresolved oracle after the mechanism exists, activate the
repository `test-design` route then; do not invent a test plan or `test_plan.md`
in this design.

## Validation mapping and exact oracles

1. **Structure**: structure contract and responsibility-scope checks pass; the only write remains this design during the current turn.
2. **Parser**: a fixture places a manifest declaration after line 80; `ManifestParser` returns it, and Python/shell consumers return the same graph edge without parsing.
3. **Scope**: a build proves `P = U ∪ X`, disjointness, and explicit exclusion reasons.
3a. **Empty scanner scope**: an isolated snapshot with `P_scan=∅` writes an
    empty `scanner-paths.txt`, the scanner emits exactly
    `CODE_DEPENDENCY_SCAN=pass files=0`, and no `git ls-files` fallback or
    relation is accepted; a missing paths file is a producer failure.
4. **Producer authority**: every `D` and `R` edge has producer/source/owner payload; graph inference is distinguishable.
5. **Graph DSL**: with `cwd=<parent-root>`, `<parent-root>/vendor/agent-canon/tools/bin/agent-canon structured-analysis graph-contract --db <parent-root>/.agent-canon/knowledge-graph/graph.sqlite --format json` returns its existing machine-readable pass result on the published DB; no PATH-installed or CWD-relative wrapper is assumed.
6. **Reverse closure**: outgoing, incoming, and both-direction queries return the same edge identity and evidence witness.
7. **Atomicity**: inject each `GraphBuildFailurePoint::{Producer,Validation,Write,Sync,Rename,DirectorySync}` seam; every pre-rename failure leaves the prior DB and status readable and removes the candidate, while post-rename directory-sync failure reports durability failure without rollback. No partial candidate becomes current.
8. **Freshness**: changing a producer artifact or source content changes status from `fresh` to `stale`; `status` does not rebuild.
9. **Completeness**: unresolved, ambiguous, uncovered, and excluded cases/counts are returned in status/query/context and never silently dropped; `O\D` and `D\O` findings are emitted per relation family.
10. **Context**: a claim token returns exact claim path, resolved source path/span, owner, dependency witness, producer, and graph fingerprint.
11. **Consumer**: `GraphClaimConsumer` at `check_design_doc_claims.py` preserves path-relative resolution and path/evidence/math classification while obtaining facts only from graph operations; with no verified `GraphIntegrationRecord`, it returns `graph-integration-unverified` and performs no claim evaluation.
12. **No R2/binder residuals**: `git grep -n -E 'bind_r2_scope|r2_scope_manifest|r2_review_closeout|R2_SCOPE_MANIFEST|R2_REVIEW_CLOSEOUT' -- rust tools documents agents .agents tests` returns no graph-route match.
13. **No byte-schema/duplicate transport residuals**: `git grep -n -E 'NormalizedRecordSet|RelationRegistryArtifact|read_normalized_record_set|normalized_record_set\.v1|relation_registry\.v1|dependency_manifest_records' -- rust tools documents agents .agents tests` returns no graph-route match; only the Graph DSL tables and `GraphFact` remain.
14. **No duplicate parser residuals**: `git grep -n -E 'parse_manifest_edges|parse_dependency_edges|strip_manifest_line|resolve_dependency_target|dependency_closure' -- tools/agent_tools rust/agent-canon/src` returns no consumer parser match, while `git grep -n 'ManifestParser' -- rust/agent-canon/src` identifies the single parser owner. The audit-listed `check_dependency_headers.py`, `check_dependency_header_format.sh`, `check_dependency_graph.sh`, `scan_dependency_headers.sh`, `vector_search.py`, `tool_drift.py`, `prose_reasoning_graph.py`, and `render_dependency_manifest_graph.py` each receive a second exact check: their dependency path invokes `agent-canon graph` or consumes its captured output, and none contains a manifest-line tokenizer or target normalizer.
15. **No residual structured/search/catalog parser**: `git grep -n -E 'has_dependency_manifest|dependency_manifest_values|dependency_coverage_rules|HEADER_SCAN_LINES|HEADER_SCAN_BYTES|strip_manifest_line|parse_dependency_edges|resolve_dependency_target|manifest_lines' -- rust/agent-canon/src/structured_analysis.rs tools/agent_tools/search_index.py tools/agent_tools/vector_search.py tools/agent_tools/tool_catalog.py tools/agent_tools/check_dependency_headers.py` returns no graph-route parser; structured-analysis inventory, search-index cards, and header checks consume graph output, while `tool_catalog.py` validates catalogs as a graph-build producer and never consumes graph output.
16. **No MCP graph route**: `git grep -n -E 'graph[^\n]*mcp|mcp[^\n]*graph' -- rust tools documents agents .agents .codex` returns no graph route, and `main.rs` exposes only the four `graph` subcommands.
17. **Cleanup**: catalog/docs/skills/dependency graph contain no public binder/normalized transport route; obsolete fixture matrices are absent only after replacement source checks pass.
18. **Two-build reproducibility**: build the same immutable parent snapshot twice, normalize away timestamps and candidate IDs, and require identical graph facts, provenance, counts, projection membership, and `public-surface` IDs/primary-secondary span sets.
19. **Add/modify/delete freshness**: add, modify, and delete one eligible source or producer artifact in isolated fixtures; require the expected `fresh`/`stale`/`missing` transition and atomic replacement behavior.
20. **Relation-family query matrix**: execute dependency, owner/scope, import/include, symbol/call, containment/document, catalog, pin/view, generated/submodule, and public relation queries in outgoing, incoming, and both directions, with bounded context for each family. Every non-`all` `RelationKind` is covered by this matrix.
21. **Adversarial/property coverage**: retain targeted cases for unsupported file types, reverse-edge asymmetry, generated/view/submodule identity, ambiguous relation joins, provenance loss, dropped producer records, and coverage-count preservation; these are post-mechanism regressions only if existing source oracles do not cover them.
22. **Runtime path normalization**: feed `read_candidate_selection_resets` absolute, drive-prefixed, `..`-escaping, NUL, separator-invalid, empty, non-UTF-8/type-invalid, non-regular, and valid `.`-normalized candidates; require the exact typed rejection codes above, root containment, no `git log` for rejected values, and accepted reset paths in normalized `RepoPath` form.
23. **Runtime measurement completeness**: a canonical dashboard fixture with every requested measurement field preserves `responsibility_unit_id`, generation parent/reuse mode, packet hash, per-source context bytes, finding/review iterations, writer/reviewer IDs, launch/finish, input/cached/output/reasoning tokens, retries, waits, progress bytes, and repeated artifact hashes with stable sorting and null-versus-zero semantics.
24. **Workflow attribution owner**: replay the hook JSONL baseline selected by `runtime_log_paths.py::hook_results_dir`; require the dashboard to report exactly 2,028 missing entries, context carry-forward separately, and no guessed workflow. A repaired event is populated by `.codex/hooks/skill_usage_logger.py::append_skill_usage_entry` and preserved by `.codex/hooks/hook_event_log.py::HookLogContext.append` through the existing `WORKFLOW_FIELDS`; the dashboard remains a consumer/checker.
25. **Token producer coverage**: use the canonical `compare_codex_token_footprints.py`/`workflow_monitor.py` artifact with no comparisons; require `comparison_count=0` plus `runtime.token_comparison_missing`, then a populated comparison fixture with exact input/cached/output/reasoning token values and no duplicate regex fact route.
26. **Runtime projection**: build with the dashboard API artifact and require `graph status`/`context` to return producer/version/hash, runtime measurement fields, typed path diagnostics, workflow/token diagnostics, and source references; raw hook/session files and runtime-result prefixes remain outside `P(S)` under explicit `X(S)`.
27. **Changed-file dependency checker**: in
    `test_check_dependency_headers.py`, record the subprocess/adapter arguments
    and require one exact status invocation followed by one exact context
    invocation per sorted checkable path, the verified
    `default`/`parent` integration pair, present=false mapping to the existing
    missing-block finding, present=true with exactly one contract and
    responsibility mapping to pass, malformed/duplicate/wrong-producer mapping
    to typed failure, and non-fresh/transport failure with no build or fallback.
    Then require
    `git grep -n -E 'HEADER_SCAN_LINES|has_dependency_manifest|has_dependency_header|strip_manifest_line|manifest_lines|registry_candidates|contract_registry_path|allowed_contract_kinds|contract_kind_findings|CONTRACT_LINE_RE|TOML_STRING_RE' -- tools/agent_tools/check_dependency_headers.py`
    to return no matches, while a positive scan finds `GraphClient` and the
    three manifest context kinds.
28. **Direct coordinated-search consumer**: `test_search.py` proves zero graph
    calls when `header-deps` is absent and exactly one
    `query(all=True,relation="dependency",direction="both",depth=0)` when it is
    selected; source and target candidates retain current scores plus
    direction/kind/reason/producer/span/evidence/authority, and non-fresh or
    malformed graph data emits `AGENT_SEARCH=fail` without fallback. Require
    `git grep -n 'vector_search.parse_dependency_edges' -- tools/agent_tools/search.py`
    to return no matches and a positive scan to find `GraphDependencyFact` and
    `GraphResponse.dependency_facts` use.
29. **Symbol-complete drift consumer**: canonical graph facts preserve the
    current missing-link, missing-direct, missing-reverse, and kind-mismatch
    findings; the tool-catalog check retains YAML/stale/legacy findings but
    never emits its own `missing-dependency-header`; one graph query supplies
    all contracts, and non-fresh status fails rather than becoming an empty
    edge set. The exact residual command
    `git grep -n -E '(^import os$|ManifestEdge|HEADER_SCAN_LINES|MANIFEST_FIELD_COUNT|MANIFEST_REASON_MAX_SPLIT|has_dependency_manifest|strip_manifest_line|repo_relative|normalize_target|manifest_edges)' -- tools/agent_tools/tool_drift.py`
    returns no matches; a positive scan finds `GraphClient`,
    `GraphDependencyFact`, and `dependency_facts`.
30. **Manual Rust dispatch and extractor grammar**: the two small
    `tool_catalog` fixtures yield exactly four sorted graph operation rows with
    graph-module primary spans and main/document secondary spans. Generated
    comment/usage, enum-derived, duplicate, missing-module, wrong-index, and
    wrong-slice mutations yield only the fixed invalid/ambiguous diagnostics
    and no partial rows. The live source contains exactly `mod graph;`, one
    current-style `args[1] == "graph"` arm calling
    `graph::run(&args[2..])`, and four graph-module literal arms calling
    `run_<operation>(&args[1..])`; CLI smoke reaches all four, while the removed
    public dependency-manifest route is unknown. Rust syntax remains gated by
    `cargo check`.
31. **Public-to-producer profile mapping**: unit tests prove omitted profile
    and explicit `--profile default` produce equal `SnapshotRequest` values and
    equal input fingerprints with producer profile `parent`; public
    `--profile parent` exits `2`. A capture spy verifies the resolved parent
    root and exact candidate artifact path. Build rejects a captured header
    profile other than `parent`; status/query/context reject a DB whose
    metadata or integration record differs from
    `profile=default,source_snapshot_profile=parent`, returning no facts.
    Producer metadata contains the exact logical command and canonical profile
    tuple, and two immutable builds preserve the same fingerprint.

These are validation items, not a post-implementation test-design packet. The
implementation worker must report command, CWD, input fixture, expected oracle,
and observed result for each applicable item.

## Review and completion gate

This artifact is complete for handoff when it contains the Abstract Design
Frame, one-unit file plan, naming plan, Source Packet, Side-Effect Map, Trace,
deletion list, reverse-edge closure, validation mapping, and dirty-intent
preservation rule above. It is not implementation-ready for the worker until a
fresh detailed-design review returns `approve` for this exact SHA and the active
document-flow review also returns `approve`.

The current branch has no PR. After approval, the implementation route is one
coherent graph/source PR containing the mechanism, consumer, docs/skills,
dependency edges, and stale-test cleanup in the order specified above. A
review `revise` returns here; `escalate` returns to planning. No implementation
or worker handoff is authorized by this document alone.

Handoff marker: `review_status=pending`; `detailed_design_review=required_same_sha`; `document_flow_review=required_same_sha`; `implementation_claim=none`.
