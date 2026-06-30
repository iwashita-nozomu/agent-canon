---
name: structure-planning
description: Use when a report, experiment plan, Eval output, presentation storyboard, PPT/deck plan, document, paper, HTML view, or refactor needs a structure contract before prose, rendering, interpretation, follow-up runs, or edits.
---
<!--
@dependency-start
contract skill
responsibility Documents Structure Planning runtime skill for this repository.
upstream design ../../../agents/skills/structure-planning.md documents the human-facing structure planning workflow
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw result and summary artifact placement
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph structure evidence handoffs
upstream design ../../../agents/workflows/slide-production-workflow.md defines PPT template, slot, and layout review workflow
@dependency-end
-->

# Structure Planning

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill structure-planning --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/structure-planning.md`.
1. Use this before drafting prose, writing a renderer, interpreting experiment output, planning a presentation/deck, planning follow-up runs, or editing refactor surfaces when the work has a nontrivial structure.
1. For document additions or revisions, use this before prose edits when section order, responsibility, claim/support, reader path, source map, or canonical route changes; for typo/link/format-only edits, record `structure_contract=skipped` with the reason and use `$md-style-check`.
1. Create a structure contract with `structure_kind`, audience, decision context, first artifact, first artifact question, `visual_plan`, source-to-structure map, `document_unit`, `document_split_decision`, OOP structure contract when planning experiments, metric or delta contract, ordered structure, invalid interpretations, and validation gate; for deck/PPT work, include slide/storyboard order and source-to-slide mapping.
1. For document structure changes, fill `document_unit` with owner, reader, source map, validation route, update cadence, canonical parent, and downstream consumers. Set `document_split_decision` to `keep`, `split`, `merge`, `inline`, `rename`, or `not_applicable:format-only` before prose edits.
1. Choose `split` only for a new owner, reader, validation route, source map, update cadence, or downstream consumer. Choose `merge`, `inline`, or `keep` when the same owner, reader, source map, validation route, and update cadence remain shared. Treat length, token budget, chunking convenience, section count, nearby path, temporary work queue, and shared validation oracle as invalid split boundaries.
1. For `experiment-plan` and `experiment-report`, structure from the OOP responsibility view before prose order: list reused modules/classes/functions/protocols, object creation/mutation/pass-through/artifact writes, the factory/function boundary where variants differ, and dependency direction across orchestration, domain logic, metrics, visualization, and artifact I/O.
1. When paragraph/block order, connective choice, or logic-gap evidence is nontrivial, run or request `agent-canon semantic-index discourse-relations --profile <general|experiment-report|methods-protocol|academic-argument|refactor-design> --format jsonl` after the semantic index is built; use it as advisory structure evidence, not as prose or policy authority.
1. If a prose graph DB or projection is present, use `prose_reasoning_graph.py explain` and `integrate` as advisory evidence for paragraph bridges, split/merge/reorder operations, and invalid interpretations.
1. Choose the first artifact before implementation: figure, table, ponchi-e/concept diagram, slide, summary card, first section, experiment slice, or refactor slice.
1. For reader-facing documents, reports, plans, workflow guides, and refactor maps, choose Mermaid as the default first visual when the structure includes nontrivial process flow, dependencies, ownership, routing, state transitions, review gates, or multi-step handoffs; choose `text-only` only when a diagram would duplicate a simple list and record that reason in `visual_plan`.
1. Map every source artifact to the section, slide, visual, claim, experiment slice, or refactor slice it supports; do not let unsupported claims or edits appear later.
1. Define metric denominator, directionality, baseline, and caveat for reports or experiments; define allowed structural delta and forbidden semantic delta for refactors.
1. Put sections, slides/storyboards, visuals, experiment slices, or refactor slices in reader or execution order rather than raw tool-output order.
1. Record invalid interpretations so the structure cannot be mistaken for policy, classification, merge, deletion, ownership, or behavior-change authority.
1. Hand the completed structure contract to `$report-writing`, `$html-output`, `$html-experiment-report`, `$experiment-lifecycle`, slide-production workflow, `$long-form-writing`, `$academic-writing`, `$paper-writing`, or `$refactor-loop` as appropriate; this skill owns structure, not raw storage, experiment execution, report prose, document drafting, implementation, or domain authority.
1. Record closeout tokens: `structure_planning=complete`, `structure_contract=<path-or-inline>`, `document_split_decision=<keep|split|merge|inline|rename|not_applicable:format-only>`, `structure_first_artifact=<name>`, `structure_visual_plan=<mermaid|table|text-only|html|image|slide|not-applicable>`, `structure_source_map=<path-or-inline>`, `structure_oop_contract=<path-or-inline|not_required>`, `discourse_relations=<path|not_required>`, and `structure_invalid_interpretations_recorded=yes`.
