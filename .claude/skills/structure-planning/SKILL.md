---
name: structure-planning
description: Use when a report, experiment plan, Eval output, document, paper, HTML view, or refactor needs a structure contract before prose, rendering, interpretation, follow-up runs, or edits.
---
<!--
@dependency-start
responsibility Documents Structure Planning runtime skill for this repository.
upstream design ../../../agents/skills/structure-planning.md documents the human-facing structure planning workflow
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw result and summary artifact placement
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph structure evidence handoffs
@dependency-end
-->

# Structure Planning

1. Read `agents/skills/structure-planning.md`.
1. Use this before drafting prose, writing a renderer, interpreting experiment output, planning follow-up runs, or editing refactor surfaces when the work has a nontrivial structure.
1. Create a structure contract with `structure_kind`, audience, decision context, first artifact, first artifact question, `visual_plan`, source-to-structure map, metric or delta contract, ordered structure, invalid interpretations, and validation gate.
1. When paragraph/block order, connective choice, or logic-gap evidence is nontrivial, run or request `agent-canon semantic-index discourse-relations --profile <general|experiment-report|methods-protocol|academic-argument|refactor-design> --format jsonl` after the semantic index is built; use it as advisory structure evidence, not as prose or policy authority.
1. If a prose graph DB or projection is present, use `prose_reasoning_graph.py explain` and `integrate` as advisory evidence for paragraph bridges, split/merge/reorder operations, and invalid interpretations.
1. Choose the first artifact before implementation: figure, table, summary card, first section, experiment slice, or refactor slice.
1. For reader-facing documents, reports, plans, workflow guides, and refactor maps, choose Mermaid as the default first visual when the structure includes nontrivial process flow, dependencies, ownership, routing, state transitions, review gates, or multi-step handoffs; choose `text-only` only when a diagram would duplicate a simple list and record that reason in `visual_plan`.
1. Map every source artifact to the section, visual, claim, experiment slice, or refactor slice it supports; do not let unsupported claims or edits appear later.
1. Define metric denominator, directionality, baseline, and caveat for reports or experiments; define allowed structural delta and forbidden semantic delta for refactors.
1. Put sections, visuals, experiment slices, or refactor slices in reader or execution order rather than raw tool-output order.
1. Record invalid interpretations so the structure cannot be mistaken for policy, classification, merge, deletion, ownership, or behavior-change authority.
1. Hand the completed structure contract to `$report-writing`, `$html-output`, `$html-experiment-report`, `$experiment-lifecycle`, `$long-form-writing`, `$academic-writing`, `$paper-writing`, or `$refactor-loop` as appropriate; this skill owns structure, not raw storage, experiment execution, report prose, document drafting, implementation, or domain authority.
1. Record closeout tokens: `structure_planning=complete`, `structure_contract=<path-or-inline>`, `structure_first_artifact=<name>`, `structure_visual_plan=<mermaid|table|text-only|html|image|not-applicable>`, `structure_source_map=<path-or-inline>`, `discourse_relations=<path|not_required>`, and `structure_invalid_interpretations_recorded=yes`.
