---
name: prose-reasoning-graph
description: Use when existing prose should be converted into a SQLite-backed structure graph, diagnosed for discourse/argument/evidence/experiment gaps, explained in natural language, and handed off to writing or review skills with split/merge/bridge/reorder rewrite packets.
---
<!--
@dependency-start
responsibility Documents Prose Reasoning Graph runtime skill for this repository.
upstream design ../../../agents/skills/prose-reasoning-graph.md documents the human-facing skill
upstream design ../../../documents/prose-reasoning-graph/dsl-spec.md normative graph and DSL contract
upstream implementation ../../../tools/agent_tools/prose_reasoning_graph.py builds graph projections and handoff packets
upstream implementation ../../../rust/agent-canon/src/structured_analysis.rs reports document responsibility gaps
upstream design ../../../documents/tools/prose_reasoning_graph.md documents CLI usage
@dependency-end
-->

# Prose Reasoning Graph

1. Read `agents/skills/prose-reasoning-graph.md`.
1. Read `documents/prose-reasoning-graph/dsl-spec.md` before interpreting,
   changing, or extending graph layers, ids, relation kinds, diagnostics,
   projections, or adapter vocabulary.
1. Preserve the DSL contract vocabulary in handoffs: source-truth anchor, lower graph, typed relation, projection view, node record, edge record, and `payload_json`.
1. Use this when prose structure, paragraph connection, claim support, evidence traceability, experiment-plan completeness, or split/merge/bridge/reorder rewrite planning should be derived from a graph rather than inferred repeatedly from raw prose.
1. Let `ingest` / `ingest-set` create the SQLite DB under `${AGENT_CANON_PROSE_GRAPH_HOME:-$HOME/.cache/agent-canon/prose-reasoning-graph}` unless the workflow explicitly passes `--db <graph.sqlite>`; generated outputs and stats still belong under the active run bundle or task-local artifact directory.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py ingest <source.md> --stats-out <ingest.stats.json>` and read `PROSE_REASONING_GRAPH_DB` from stdout or the stats JSON.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py analyze --db <graph.sqlite> --profile <writing|logic|experiment|report|academic|paper|all> --stats-out <analyze.stats.json>`.
1. When judging whether repository documents satisfy their dependency-manifest responsibility, materialize Rust `structured-analysis` `document-canon` diagnostics in the graph DB and route them through the same diagnostic, integration, verification, and rewrite loop as prose findings.
1. Treat `edit_operations` as optional for structured-analysis DBs. `project`, `lint`, `explain`, and `integrate` must still read document-canon diagnostics when operations count is `0`; use `rewrite-packet --op <operation-id>` only when the DB contains a concrete edit operation.
1. Keep stdout token-light: never print full projection, diagnostics, explanation, integration, handoff, or rewrite structures to chat or CLI stdout. Write them with `--out`, add `--stats-out`, read the stats JSON first, and open larger artifacts only as needed.
1. For concrete edits, use `rewrite-packet --op <operation-id>` so the LLM receives target ids, reason, preserve constraints, and do-not rules.
1. Use `skill-handoff` to route graph evidence to `$long-form-writing`, `$report-writing`, `$academic-writing`, `$paper-writing`, `$literature-survey`, `$structure-planning`, `$formal-proof-workflow`, `logic-gap-review`, `citation-evidence-review`, `$experiment-lifecycle`, and `$result-artifact-writeout` without replacing their authority.
1. When diagnostics mark uncertain logic, unsupported claims, missing warrants, weak paragraph connections, or document responsibility gaps, send them through the emitted verification route before rewrite: use `logic-gap-review` for inference validity, `$literature-survey` / `citation-evidence-review` for external evidence, `$formal-proof-workflow` for mathematical/proof-like or implementation-derived claims, `$experiment-lifecycle` for testable empirical claims, `$structure-planning` for reader-state or discourse-connection checks, and `document_responsibility_verification` for dependency-manifest coverage gaps.
1. Expand verification routes recursively inside this skill: decompose each unresolved route into child questions, route each child to the listed verifier, rerun graph diagnostics after verified evidence or limitations are added, and repeat until every leaf is verified, explicitly limited, or recorded as an unresolved blocker/warn. Do not let unresolved leaves become settled prose.
1. For writing-skill handoffs, close findings at the DSL/projection stage before writing final prose: run diagnostics/integration, revise the structure contract or graph-backed rewrite packet, re-ingest or rerun analysis, and loop until active findings for the selected profile are gone. Only then write reader-facing prose. If the same finding class persists after targeted structure rewrites, record a `prompt-defect` finding against the sentence-generation or section-generation prompt instead of continuing blindly.
1. Treat graph diagnostics as advisory: they identify unsupported claims, weak bridges, missing experiment fields, and candidate edit operations, but they do not approve citations, rewrite final prose, settle logic reviews, or change policy by themselves.
1. Record closeout tokens: `prose_graph_db=<path>`, `prose_graph_projection=<path>`, `prose_graph_diagnostics=<path>`, `prose_graph_explanation=<path>`, `prose_graph_integration_plan=<path>`, `prose_graph_handoff=<path>`, `prose_graph_rewrite_packet=<path|not_required>`, and `prose_graph_stats=<path>`.
