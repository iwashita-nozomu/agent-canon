---
name: prose-reasoning-graph
description: Use when existing prose should be converted into a SQLite-backed structure graph, diagnosed for discourse/argument/evidence/experiment gaps, explained in natural language, and handed off to writing or review skills with split/merge/bridge/reorder rewrite packets.
---
<!--
@dependency-start
contract skill
responsibility Documents Prose Reasoning Graph runtime skill for this repository.
upstream design ../../../agents/skills/prose-reasoning-graph.md documents the human-facing skill
upstream design ../../../documents/prose-reasoning-graph/dsl-spec.md normative graph and DSL contract
upstream implementation ../../../tools/agent_tools/prose_reasoning_graph.py builds graph projections and handoff packets
upstream implementation ../../../rust/agent-canon/src/structured_analysis.rs reports document responsibility gaps
upstream design ../../../documents/tools/prose_reasoning_graph.md documents CLI usage
@dependency-end
-->

# Prose Reasoning Graph

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill prose-reasoning-graph --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/prose-reasoning-graph.md`.
1. Read `documents/prose-reasoning-graph/dsl-spec.md` before interpreting,
   changing, or extending graph layers, ids, relation kinds, diagnostics,
   projections, or adapter vocabulary.
1. Preserve the DSL contract vocabulary in handoffs: source-truth anchor, lower graph, typed relation, projection view, node record, edge record, and `payload_json`.
1. Use this when prose structure, paragraph connection, claim support, evidence traceability, experiment-plan completeness, or split/merge/bridge/reorder rewrite planning should be derived from a graph rather than inferred repeatedly from raw prose.
1. Use this as the structure-first writing gate for nontrivial or substantive document creation or revision: encode the draft or source packet into the graph/DSL, analyze it, expand/delete/reorganize graph-backed structure while it is still DSL/projection state, rerun diagnostics, and only then project to reader-facing prose.
1. Skip this gate only for typo, link, Markdown formatting, or other format-only edits that do not change section order, responsibility coverage, claim/support, reader path, source map, or canonical route; record that reason and use `$md-style-check` for those edits.
1. Treat corpus management and existing-document-to-DSL seed extraction as LocalLLM tasks. `ingest` / `ingest-set` call `agent-canon local-llm extract-prose-ir`, which partitions multiple documents and terms into bounded parts, writes `local_llm_prose_ir`, and merges `corpus_hints`, `term_contexts`, and `dsl_seed` into graph metadata. Do not revive fixed keyword dictionaries or ask the LLM to return raw word lists in chat.
1. Let `ingest` / `ingest-set` create the SQLite DB under `${AGENT_CANON_PROSE_GRAPH_HOME:-$HOME/.cache/agent-canon/prose-reasoning-graph}` unless the workflow explicitly passes `--db <graph.sqlite>`; generated outputs and stats still belong under the active run bundle or task-local artifact directory.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py ingest <source.md> --stats-out <ingest.stats.json>` and read `PROSE_REASONING_GRAPH_DB` from stdout or the stats JSON.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py analyze --db <graph.sqlite> --profile <writing|logic|experiment|report|academic|paper|all> --stats-out <analyze.stats.json>`.
1. When judging whether one repository document satisfies its dependency-manifest responsibility, prefer `python3 tools/agent_tools/prose_reasoning_graph.py check-document <source.md> --out-dir <artifact-dir> --profile <profile> --stats-out <stats.json>`. This single tool path runs prose analysis and Rust `structured-analysis` document-canon checking before writing diagnostics, explanation, integration, handoff, and a combined report.
1. For broader or already-materialized structured-analysis DBs, materialize Rust `structured-analysis` `document-canon` diagnostics in the graph DB and route them through the same diagnostic, integration, verification, and rewrite loop as prose findings.
1. Treat `edit_operations` as optional for structured-analysis DBs. `project`, `lint`, `explain`, and `integrate` must still read document-canon diagnostics when operations count is `0`; use `rewrite-packet --op <operation-id>` only when the DB contains a concrete edit operation.
1. Keep stdout token-light: never print full projection, diagnostics, explanation, integration, handoff, or rewrite structures to chat or CLI stdout. Write them with `--out`, add `--stats-out`, read the stats JSON first, and open larger artifacts only as needed.
1. Treat tool results as bounded contracts: `ingest` / `ingest-set` returns `PROSE_REASONING_GRAPH_DB` and `PROSE_REASONING_GRAPH_LOCAL_LLM_IR`, `analyze` mutates the DB and returns stats, `check-document --out-dir` returns a combined document-check report plus `PROSE_REASONING_GRAPH_DOCUMENT_CANON_FINDINGS`, `lint --out` returns active diagnostics with severity/rule/target/verification route, `integrate --out` returns operation count plus recursive verification routes, `skill-handoff --out` returns receiving-skill packets, and `project --out` is reserved for full graph inspection.
1. If `integrate` reports `operations: 0`, continue with diagnostic verification and rerun checks; do not call `rewrite-packet` until a concrete operation id exists.
1. Do not treat `PROSE_REASONING_GRAPH_EDIT_OPERATIONS=0` as `no findings`. Always inspect diagnostic rules and counts. If any `presentation_format_candidate` remains, record each target, recommended format, feature-subgraph reason, verification route, and decision status before closeout.
1. A `presentation_format_candidate` is unresolved until `$structure-planning` / `$report-writing` has adopted it, rejected it with renderer or reader-state evidence, combined it with prose, or preserved it as an explicit unresolved warning with owner and next command. Do not summarize it as a harmless residual warning without that decision record.
1. For concrete edits, use `rewrite-packet --op <operation-id>` so the LLM receives target ids, reason, preserve constraints, and do-not rules.
1. Use `skill-handoff` to route graph evidence to `$long-form-writing`, `$report-writing`, `$academic-writing`, `$paper-writing`, `$literature-survey`, `$structure-planning`, `$formal-proof-workflow`, `logic-gap-review`, `citation-evidence-review`, `$experiment-lifecycle`, and `$result-artifact-writeout` without replacing their authority.
1. For DSL-to-prose projection, pass the `project --out` payload's `selected_ordering.ordered_anchors` to the receiving writing skill as the whole-document sentence sequence. This field is the priority topological sort over the selected ordering subgraph and is the deterministic reader-order contract for the prose-writing LLM.
1. When diagnostics mark uncertain logic, unsupported claims, missing warrants, weak paragraph connections, feature-subgraph-backed presentation format candidates, or document responsibility gaps, send them through the emitted verification route before rewrite: use `logic-gap-review` for inference validity, `$literature-survey` / `citation-evidence-review` for external evidence, `$formal-proof-workflow` for mathematical/proof-like or implementation-derived claims, `$experiment-lifecycle` for testable empirical claims, `$structure-planning` for reader-state, discourse-connection, or presentation-format checks, and `document_responsibility_verification` for dependency-manifest coverage gaps.
1. Expand verification routes recursively inside this skill: decompose each unresolved route into child questions, route each child to the listed verifier, rerun graph diagnostics after verified evidence or limitations are added, and repeat until every leaf is verified, explicitly limited, or recorded as an unresolved blocker/warn. Do not let unresolved leaves become settled prose.
1. For writing-skill handoffs, close findings at the DSL/projection stage before writing final prose: run diagnostics/integration, revise the structure contract or graph-backed rewrite packet, add missing nodes/edges, remove unsupported nodes, split/merge/reorder projection units, route presentation candidates to adoption/rejection/defer decisions, re-ingest or rerun analysis, and loop until active findings for the selected profile are gone or explicitly recorded as unresolved warnings with owners.
1. After DSL/projection closure, let the receiving writing skill project to prose, then rerun `check-document` or the same ingest/analyze/lint path. If new findings appear that were absent from the closed DSL/projection state, record `dsl_to_prose_prompt_defect` against the sentence-generation, section-generation, or DSL-to-prose prompt and repair that prompt before more prose rewriting.
1. Treat graph diagnostics as advisory: they identify unsupported claims, weak bridges, missing experiment fields, and candidate edit operations, but they do not approve citations, rewrite final prose, settle logic reviews, or change policy by themselves.
1. Record closeout tokens: `prose_graph_db=<path>`, `prose_graph_projection=<path|not_required>`, `prose_graph_document_check=<path|not_required>`, `prose_graph_diagnostics=<path>`, `prose_graph_explanation=<path>`, `prose_graph_integration_plan=<path>`, `prose_graph_handoff=<path>`, `prose_graph_rewrite_packet=<path|not_required>`, `prose_graph_presentation_decisions=<path|none>`, and `prose_graph_stats=<path>`.
