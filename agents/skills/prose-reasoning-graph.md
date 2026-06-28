# prose-reasoning-graph
<!--
@dependency-start
contract skill
responsibility Documents prose-reasoning-graph analysis, source-truth graph contract, diagnostics, verification routes, presentation decisions, and skill handoff workflow.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design ../../documents/prose-reasoning-graph/dsl-spec.md normative source truth graph, DSL, projection, verification route, presentation decision, evidence, and responsibility contract
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py builds SQLite-backed graph projections, diagnostics, evidence support, presentation candidates, integration operations, rewrite-packet operation ids, and skill handoff packets
downstream implementation ../../rust/agent-canon/src/structured_analysis.rs reports document responsibility gaps and dependency-manifest coverage diagnostics
downstream implementation ../../.agents/skills/prose-reasoning-graph/SKILL.md exposes this workflow as a runtime skill with diagnostics, recursive verification, unresolved leaf policy, presentation decision, and closeout evidence rules
downstream design ../../documents/tools/prose_reasoning_graph.md documents CLI usage, stats artifacts, runtime result contract, and handoff boundaries
@dependency-end
-->

## Reader Map

- Purpose: analyze prose as a typed graph before rewriting, reviewing, or
  handing it to writing and research skills.
- Section path: Purpose defines the graph boundary table; Use When selects the
  task shape; Standard Sequence gives the operational flow; Runtime Tool Result
  Contract, Required Outputs, and Literature Boundary define outputs and limits.
- Use when: section order, reader path, claim support, split/merge/bridge
  decisions, logic holes, or graph-backed rewrite packets need evidence.
- Boundary: graph artifacts preserve source truth and prepare handoff; they do
  not replace the receiving writing, research, proof, or review skill.

## Purpose

`prose-reasoning-graph` is the overlay skill for analyzing prose as a typed
graph before asking an LLM or writing skill to rewrite it. It converts existing
Markdown/plain text into a SQLite-backed intermediate graph, runs layer
diagnostics, explains graph findings in natural language, and emits handoff
packets for existing writing, research, review, experiment, and artifact skills.

| Boundary | Responsibility |
| -------- | -------------- |
| DSL contract | [documents/prose-reasoning-graph/dsl-spec.md](../../documents/prose-reasoning-graph/dsl-spec.md) owns layer, relation, identifier, projection, validation, and adapter vocabulary. This skill owns when and how to use the graph while preserving source-truth anchors and source spans. |
| Graph contract | Sentence or EDU anchors and their typed relations are canonical for prose content. Macro-claims, rhetorical moves, reader-state transitions, sections, and paragraphs are projection or form views, not replacement source truth. |
| Handoff vocabulary | Handoff packets preserve source truth, lower graph, typed relation, projection view, node record, edge record, and `payload_json`. |
| Presentation candidates | Projection views may recommend prose, lists, tables, figures, or equations. Non-prose forms remain verified `presentation_format_candidate` decisions over source anchors, not provenance-dropping rewrites. |
| LocalLLM boundary | `ingest` / `ingest-set` call `agent-canon local-llm extract-prose-ir` to split documents and terms, extract `local_llm_prose_ir`, and merge `corpus_hints`, `term_contexts`, and `dsl_seed` into graph metadata. Fixed keyword dictionaries are not the corpus source. |
| Receiving skill boundary | Graph artifacts prepare handoff to `$long-form-writing`, `$report-writing`, `$academic-writing`, `$paper-writing`, `$literature-survey`, `$structure-planning`, `$formal-proof-workflow`, `logic-gap-review`, `citation-evidence-review`, `$experiment-lifecycle`, and `$result-artifact-writeout`; they do not replace those skills' authority. |
| Document responsibility adapter | Rust `structured-analysis` emits `document-canon` diagnostics such as `document_responsibility_gap`; prose graph commands import them into the same diagnostic, integration, verification, and rewrite loop. Diagnostics-only DBs still use `project`, `lint`, `explain`, and `integrate`, while `rewrite-packet` requires a concrete operation id. |

## Use When

- Existing prose should be converted into a graph/DSL-like intermediate form.
- Paragraph order, paragraph-to-paragraph connection, or paragraph-internal
  naturalness needs evidence before rewrite.
- A draft or substantive document addition/revision needs split, merge, bridge,
  reorder, responsibility-coverage, or reader-path decisions before prose is
  added.
- A paper, scholarly note, report, or experiment plan needs logic-hole,
  citation/evidence, or experiment-design triage before drafting.
- An LLM should receive a compact rewrite packet rather than re-inferring the
  whole document structure from raw prose.

## Standard Sequence

This skill is the structure-first writing gate. For nontrivial or substantive
document creation or revision, do not ask a writing skill to draft
reader-facing prose from raw notes while graph findings are still open. Typos,
link fixes, Markdown formatting, and other format-only edits may skip this gate
when they do not change section order, responsibility coverage, claim/support,
reader path, source map, or canonical route.

1. Encode the draft or source packet into the graph/DSL.
1. Analyze the graph.
1. Expand, delete, or reorganize graph-backed structure while it is still
   DSL/projection state.
1. Rerun diagnostics.
1. Project to prose only after graph findings are closed or explicitly owned.
1. Rerun the same graph check after projection.
1. Classify findings that appear only after DSL-to-prose projection as
   `dsl_to_prose_prompt_defect` against the receiving writing skill prompt.

1. Let `ingest` or `ingest-set` create the graph DB under
   `${AGENT_CANON_PROSE_GRAPH_HOME:-$HOME/.cache/agent-canon/prose-reasoning-graph}`
   unless the workflow explicitly passes `--db <graph.sqlite>`. Store
   generated outputs and stats under the active run bundle, report, or other
   task-local artifact directory.
1. Run `ingest` on the source Markdown/plain text with `--prompt` or
   `--prompt-file` when user request context can identify the intended corpus.
   Always use `--stats-out`, then pass the emitted
   `PROSE_REASONING_GRAPH_DB` path to later graph commands. The same stats
   artifact also carries `PROSE_REASONING_GRAPH_LOCAL_LLM_IR`; keep that JSON
   as the structure/corpus extraction artifact instead of asking the LLM to
   return raw word lists in chat.
1. Run `analyze --profile <writing|logic|experiment|report|academic|paper|all>`
   with `--stats-out`. This derives prose, logic, evidence, experiment, and
   presentation layers.
1. When the task also judges whether repository documents satisfy their declared
   responsibility, prefer `check-document <source.md> --out-dir <artifact-dir>`
   instead of running the prose and document-canon paths by hand. It runs prose
   ingest/analysis, Rust `structured-analysis build`, target document-canon
   import, diagnostics, explanation, integration, handoff, and combined report
   export through one bounded tool path. A structured-analysis DB does not have
   to contain `edit_operations`; operations count `0` is valid for
   responsibility-only diagnosis.
1. Export `project`, `lint`, `explain`, and `integrate` outputs with `--out`
   and `--stats-out`; read the stats JSON before opening larger artifacts.
   Do not print full projection, diagnostics, explanation, integration,
   handoff, or rewrite structures to chat or CLI stdout.
   Do not treat `PROSE_REASONING_GRAPH_EDIT_OPERATIONS=0` as `no findings`.
   Always inspect diagnostic rules and counts. If diagnostics include
   `presentation_format_candidate`, record each target, recommended format,
   feature-subgraph reason, verification route, and decision status before
   closeout.
1. For each proposed operation that should be rewritten, export
   `rewrite-packet --op <operation-id>`. Skip this step when the current DB has
   only diagnostics and no edit-operation ids.
1. Export `skill-handoff` and pass it to the receiving skill or reviewer.
1. For DSL-to-prose projection, pass the `project --out` payload's
   `selected_ordering.ordered_anchors` to the receiving writing skill as the
   whole-document sentence sequence. The ordering is a priority topological sort
   over the selected ordering subgraph, so the LLM receives a deterministic reader-order contract
   before it writes sentences or sections.
1. If diagnostics include a verification route, verify before rewrite:
   `logic-gap-review` checks inference validity, `$literature-survey` and
   `citation-evidence-review` check external evidence, `$formal-proof-workflow`
   checks mathematical/proof-like or implementation-derived claims,
   `$experiment-lifecycle` checks testable empirical claims, and
   `$structure-planning` checks reader-state, discourse-connection validity, or
   feature-subgraph-backed presentation format candidates.
   `document_responsibility_verification` expands dependency-manifest coverage
   rules, maps each missing group to the downstream document span that should
   carry it, and reruns `structured-analysis` to close or preserve the finding.
1. Expand verification recursively inside this skill. For each unresolved
   route, create child questions from the route's recursive steps, hand each
   child to the listed verifier, add verified evidence or limitations back into
   the structure packet, rerun graph diagnostics, and repeat until every leaf is
   verified, explicitly limited, or recorded as an unresolved blocker/warn.
   Unresolved leaves must not become settled prose.
   A `presentation_format_candidate` remains unresolved until
   `$structure-planning` / `$report-writing` has adopted it, rejected it with
   renderer or reader-state evidence, combined it with prose, or preserved it as
   an explicit unresolved warning with owner and next command.
1. When the receiving skill is a writing skill, rerun graph diagnostics after
   each DSL/projection rewrite and keep looping until active findings for the
   selected profile are gone. Revise the structure contract, graph-backed
   rewrite packet, or source draft at the structural layer: add missing nodes or
   edges, remove unsupported nodes, split or merge projection units, reorder the
   projection, route verification children, or decide presentation candidates.
   Only after that closure may the receiving skill write final prose. After
   prose projection, rerun `check-document` or the same ingest/analyze/lint
   path. If new findings appear that were absent from the closed
   DSL/projection state, record a
   `dsl_to_prose_prompt_defect` finding against the sentence-generation,
   section-generation, or DSL-to-prose prompt and repair that prompt before more
   prose rewriting.
1. Treat graph diagnostics as advisory evidence. Final prose, review, and
   publication authority stays with the receiving skill.

## Runtime Tool Result Contract

Runtime agents use the tool as a black box through bounded result artifacts.
They do not need to read the tool design document during ordinary execution.
The skill contract is:

| Command | Runtime result | How the skill consumes it |
| ------- | -------------- | ------------------------- |
| `ingest` / `ingest-set` | Pass marker plus stats JSON containing `PROSE_REASONING_GRAPH_DB`; DB stored under the default cache unless `--db` is explicit. | Save the DB path and pass it to later commands. Do not read raw SQLite tables. |
| `agent-canon local-llm extract-prose-ir` | LocalLLM prose IR JSON with `parts[]`, `documents[]`, `terms[]`, `corpus_hints`, and `dsl_seed`. | Treat as the corpus-management and existing-document-structure extraction artifact. Read it through graph metadata or stats path, not chat stdout. |
| `analyze` | Pass marker plus stats JSON; graph layers are added or refreshed inside the DB. | Treat the DB as updated intermediate state. Do not stream graph contents to chat. |
| `lint --out` | Diagnostics Markdown plus stats JSON. | Read severity, rule, target, message, and `verification_route` summaries; classify active findings before rewrite. |
| `integrate --out` | Integration Markdown with operation count and verification routes. | Follow recursive verification routes first. Operations count `0` is valid for structured-analysis DBs that contain diagnostics without rewrite operations. |
| `skill-handoff --out` | Handoff Markdown naming receiving skills, DB path, projection fields, diagnostics, and routes. | Pass the bounded packet to the receiving skill; do not replace that skill's authority. |
| `rewrite-packet --op` | One bounded rewrite packet with target ids, reason, preserve constraints, and do-not rules. | Use only when `integrate` exposed a concrete operation id. Skip for diagnostics-only DBs. |
| `project --out` | Full projection JSON/YAML. | Reserve for reviewers or implementers that need complete graph evidence; default runtime flow reads stats, diagnostics, integration, and handoff first. |
| `explain --out` | Natural-language graph explanation. | Use for user-facing or reviewer-readable summaries after diagnostics are already classified. |
| `check-document --out-dir` | Combined document-check report plus diagnostics, explanation, integration, handoff, stats, and `PROSE_REASONING_GRAPH_DOCUMENT_CANON_FINDINGS`. | Use when judging whether one document both reads coherently and satisfies its declared document responsibility. Read stats first, then the combined report and active diagnostics. |

Full projection, diagnostics, explanation, integration, handoff, and rewrite
packet bodies must be written with `--out`. Stdout is a status channel for pass
markers and artifact paths.

## Required Outputs

```text
prose_graph_db=<path>
prose_graph_projection=<path>
prose_graph_diagnostics=<path>
prose_graph_explanation=<path>
prose_graph_integration_plan=<path>
prose_graph_handoff=<path>
prose_graph_rewrite_packet=<path|not_required>
prose_graph_presentation_decisions=<path|none>
prose_graph_stats=<path>
```

## Literature Boundary

The graph layers are intentionally plural.

| Literature family | Layer motivation |
| ----------------- | ---------------- |
| RST | Rhetorical relations and nucleus/satellite-style organization. |
| PDTB | Local discourse relations. |
| Annotation Graphs | Source-span anchored overlays. |
| eRST and RST dependency views | Graph-shaped discourse overlays. |
| Toulmin / AIF | Claim/evidence reasoning. |
| Argumentative zoning | Scholarly move labels. |
| Reproducible experiment literature | Hypothesis, metric, and baseline planning. |

Do not collapse these layers into one total order until a projection or
receiving skill asks for reader order.
