---
name: report-writing
description: Use when drafting or revising reader-facing reports from tool, hook, eval, experiment, review, audit, or operational evidence; separates raw-result writeout from report narrative and applies the report quality checklist.
---
<!--
@dependency-start
responsibility Documents Report Writing runtime skill for this repository.
upstream design ../../../agents/skills/report-writing.md documents the human-facing report-writing workflow
upstream design ../../../agents/skills/structure-planning.md defines report structure contracts
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw result and summary artifact placement
downstream design ../../../agents/skills/html-output.md consumes report content for explicit HTML rendering and browser publication
downstream design ../../../agents/evals/report_quality_eval.toml defines report quality checklist eval coverage
downstream implementation ../../../tools/agent_tools/evaluate_report_quality.py evaluates report-writing prompt surfaces
@dependency-end
-->

# Report Writing

1. Read `agents/skills/report-writing.md`.
1. Classify the report before writing: `status-report`, `evaluation-report`, `experiment-report`, `review-report`, `audit-report`, `decision-brief`, or `improvement-guide`.
1. Choose output format: default to Markdown unless the user explicitly asks for HTML, browser view, dashboard, web page, or external browser publication. If HTML is explicit, use `$html-output` after the source packet and structure are fixed.
1. Build a source packet with audience, decision context, source artifacts, observed facts, inferred claims, limitations, provenance, and requested next action.
1. Use `$structure-planning` before drafting when the report has a nontrivial reader structure, first figure/table, comparison, metric interpretation, source-to-section map, or invalid interpretation boundary.
1. When `$structure-planning` is active, use its structure contract as the report skeleton and do not add sections or claims that lack mapped evidence, an explicit inference label, or a stated limitation.
1. If the report uses external references, first inspect existing repo reference notes and cite/update those durable source packets; a browser tab, downloaded temp file, or chat-only source summary is not enough provenance.
1. Use `$result-artifact-writeout` when the task also writes raw machine results, append-only eval evidence, hook logs, or experiment artifacts; do not treat the reader report as the raw evidence store.
1. Apply the Report Quality Checklist: audience and decision fit, purpose and non-goals, evidence traceability, observation/interpretation separation, claim strength, limitations and uncertainty, provenance, actionability, artifact integrity, and rule-drift control.
1. For `evaluation-report` and `experiment-report`, include a reader guide before detailed results. The guide must state what to inspect first, each key metric's denominator and directionality, which comparisons are valid or invalid, the main caveat, and what result would change the next action.
1. Mark every recommendation or claim with a source path, stable artifact id, command, or explicit `inference` label.
1. Keep generated reports out of policy truth. If a report changes a rule, update the canonical skill, workflow, tool, or document and cite the report as evidence.
1. For claim-heavy, external-facing, or high-impact reports, route a read-only `report_reviewer` pass before closeout and store the review artifact path.
1. Record closeout tokens: `report_writing=complete`, `report_output_format=<markdown|html>`, `report_quality_checklist=pass|fail`, `report_source_packet=<path-or-inline>`, `structure_contract=<path|inline|not_required>`, `report_reviewer=<path|not_required>`, and `report_rule_drift=<none|canonical_update_required>`.
