---
name: report-writing
description: Use when drafting or revising reader-facing reports, decision briefs, experiment summaries, presentation narratives, PPT/storyboard plans, or slide-ready visual asset plans from tool, hook, eval, experiment, review, audit, or operational evidence; separates raw-result writeout from report narrative and applies the report quality checklist.
---
<!--
@dependency-start
contract skill
responsibility Documents Report Writing runtime skill for this repository.
upstream design ../../../agents/skills/report-writing.md documents the human-facing report-writing workflow
upstream design ../../../agents/skills/structure-planning.md defines report structure contracts
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw result and summary artifact placement
upstream design ../../../agents/skills/prose-reasoning-graph.md defines graph diagnostics and skill handoff packets
upstream design ../../../agents/workflows/slide-production-workflow.md defines PPT template, slot, and layout review workflow
downstream design ../../../agents/skills/html-output.md consumes report content for explicit HTML rendering and browser publication
downstream design ../../../evidence/agent-evals/report_quality_eval.toml defines report quality checklist eval coverage
downstream implementation ../../../tools/agent_tools/evaluate_report_quality.py evaluates report-writing prompt surfaces
@dependency-end
-->

# Report Writing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill report-writing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/report-writing.md`.
1. Select this as the DSL-to-prose projection adapter when file/document responsibility is evidence-backed status, audit, evaluation, review, decision, recommendation, or operational report; do not select it by length.
1. Classify the report before writing: `status-report`, `evaluation-report`, `experiment-report`, `review-report`, `audit-report`, `decision-brief`, `presentation-narrative`, `ppt-storyboard`, or `improvement-guide`.
1. Choose output format: default to Markdown unless the user explicitly asks for HTML, browser view, dashboard, web page, external browser publication, or a slide deck/PPT. If HTML is explicit, use `$html-output` after the source packet and structure are fixed; if a deck or PPT is in scope, use the slide-production workflow after the report source packet is fixed.
1. Build a source packet with audience, decision context, source artifacts, observed facts, inferred claims, limitations, provenance, requested next action, and any presentation asset needs such as ponchi-e/concept diagrams, slide figures, storyboard order, template slots, references, and preview artifacts.
1. Use `$structure-planning` before drafting when the report has a nontrivial reader structure, first figure/table/ponchi-e, presentation storyboard, comparison, metric interpretation, source-to-section map, source-to-slide map, or invalid interpretation boundary.
1. When the report explains workflow, dependency, ownership, routing, state transition, review gate, handoff, or multi-step evidence flow, have `$structure-planning` set a `visual_plan` and use Mermaid as the default first visual unless a table or text-only outline is clearer.
1. When `$structure-planning` is active, use its structure contract as the report skeleton and do not add sections or claims that lack mapped evidence, an explicit inference label, or a stated limitation; if it records `discourse_relations=<path>`, use those edge scores to check paragraph order and transition claims.
1. For nontrivial report creation or revision, create or receive a `$prose-reasoning-graph` handoff before drafting report prose; for an existing repository Markdown report, use `check-document` so prose diagnostics and document-canon diagnostics are generated together.
1. Read prose graph projection, diagnostics, explanation, and integration plan as advisory evidence for reader flow, unsupported claims, paragraph bridges, and split/merge/reorder operations; keep the report source packet authoritative for factual claims.
1. When the prose graph handoff includes `selected_ordering.ordered_anchors`, use that whole-document topological sentence order as the DSL-to-prose input sequence before drafting report sections or paragraph transitions.
1. Project report responsibilities into positive prose contracts: state what the report observes, infers, recommends, limits, and hands off. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Before writing report prose, close `fix-now` findings at the DSL/projection stage: revise the structure contract, source-to-section map, graph-backed rewrite packet, or graph-backed units, rerun graph diagnostics, and only draft report prose after the selected profile has no active findings.
1. After projecting DSL/projection state to report prose, rerun the graph check. If new findings appear only after projection, record `dsl_to_prose_prompt_defect` against this skill's report prose-generation prompt and repair that prompt before continuing.
1. If the report uses external references, first inspect existing repo reference notes and cite/update those durable source packets; a browser tab, downloaded temp file, or chat-only source summary is not enough provenance.
1. Use `$result-artifact-writeout` when the task also writes raw machine results, append-only eval evidence, hook logs, or experiment artifacts; do not treat the reader report as the raw evidence store.
1. For external presentations, include a presentation asset packet before prose or slide drafting. It must list the core story, first visual, required ponchi-e/concept diagrams, data-backed figures, generated-image prompts or asset paths, slide slot mapping, reference/footnote plan, and layout/preview gate.
1. Run a finding-closure loop before accepting the report: draft or revise, run the applicable graph/review/report-quality checker, classify every finding, rewrite targeted text for every `fix-now` finding, and rerun until no active findings remain.
1. If the same finding class persists after repeated targeted rewrites, do not continue blindly and do not mark the report complete. Record a `prompt-defect` finding against the sentence-generation or section-generation prompt and make prompt repair the next work item.
1. Apply the Report Quality Checklist: audience and decision fit, purpose and non-goals, evidence traceability, observation/interpretation separation, claim strength, limitations and uncertainty, provenance, actionability, artifact integrity, presentation asset traceability, and rule-drift control.
1. Keep Mermaid diagrams as fenced `mermaid` blocks with nearby prose stating what the diagram answers and what it does not claim.
1. For `evaluation-report` and `experiment-report`, include a reader guide before detailed results. The guide must state what to inspect first, each key metric's denominator and directionality, which comparisons are valid or invalid, the main caveat, and what result would change the next action.
1. Mark every recommendation or claim with a source path, stable artifact id, command, or explicit `inference` label.
1. Keep generated reports out of policy truth. If a report changes a rule, update the canonical skill, workflow, tool, or document and cite the report as evidence.
1. For claim-heavy, external-facing, slide-backed, or high-impact reports, route a read-only `report_reviewer` pass before closeout and store the review artifact path. For PPT/deck output, also require a layout review for generated images, equations, references, and slide previews.
1. Record closeout tokens: `report_writing=complete`, `report_output_format=<markdown|html|deck|ppt>`, `report_quality_checklist=pass|fail`, `report_source_packet=<path-or-inline>`, `presentation_asset_packet=<path|inline|not_required>`, `structure_contract=<path|inline|not_required>`, `report_reviewer=<path|not_required>`, and `report_rule_drift=<none|canonical_update_required>`.
