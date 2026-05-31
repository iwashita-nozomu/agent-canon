---
name: prose-reasoning-graph
description: Use when existing prose should be converted into a SQLite-backed structure graph, diagnosed for discourse/argument/evidence/experiment gaps, explained in natural language, and handed off to writing or review skills with split/merge/bridge/reorder rewrite packets.
---
<!--
@dependency-start
responsibility Documents Prose Reasoning Graph runtime skill for this repository.
upstream design ../../../agents/skills/prose-reasoning-graph.md documents the human-facing skill
upstream implementation ../../../tools/agent_tools/prose_reasoning_graph.py builds graph projections and handoff packets
upstream design ../../../documents/tools/prose_reasoning_graph.md documents CLI usage
@dependency-end
-->

# Prose Reasoning Graph

1. Read `agents/skills/prose-reasoning-graph.md`.
1. Use this when prose structure, paragraph connection, claim support, evidence traceability, experiment-plan completeness, or split/merge/bridge/reorder rewrite planning should be derived from a graph rather than inferred repeatedly from raw prose.
1. Store the SQLite DB and generated outputs under the active run bundle or task-local artifact directory; the graph DB is an intermediate artifact, not a durable source of truth.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py ingest <source.md> --db <graph.sqlite> --stats-out <ingest.stats.json>`.
1. Run `python3 tools/agent_tools/prose_reasoning_graph.py analyze --db <graph.sqlite> --profile <writing|logic|experiment|report|academic|paper|all> --stats-out <analyze.stats.json>`.
1. Export `project`, `lint`, `explain`, and `integrate` outputs with `--stats-out` before asking an LLM or receiving skill to rewrite prose; read the stats JSON first and open larger artifacts only as needed.
1. For concrete edits, use `rewrite-packet --op <operation-id>` so the LLM receives target ids, reason, preserve constraints, and do-not rules.
1. Use `skill-handoff` to route graph evidence to `$long-form-writing`, `$report-writing`, `$academic-writing`, `$paper-writing`, `$literature-survey`, `$structure-planning`, `logic-gap-review`, `citation-evidence-review`, `$experiment-lifecycle`, and `$result-artifact-writeout` without replacing their authority.
1. Treat graph diagnostics as advisory: they identify unsupported claims, weak bridges, missing experiment fields, and candidate edit operations, but they do not approve citations, rewrite final prose, settle logic reviews, or change policy by themselves.
1. Record closeout tokens: `prose_graph_db=<path>`, `prose_graph_projection=<path>`, `prose_graph_diagnostics=<path>`, `prose_graph_explanation=<path>`, `prose_graph_integration_plan=<path>`, `prose_graph_handoff=<path>`, `prose_graph_rewrite_packet=<path|not_required>`, and `prose_graph_stats=<path>`.
