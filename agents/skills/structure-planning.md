# structure-planning
<!--
@dependency-start
responsibility Documents reusable structure planning for reports, experiments, documents, and refactors.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design prose-reasoning-graph.md prose graph overlay and handoff contract
upstream design ../workflows/slide-production-workflow.md slide template, slot, and layout review workflow
downstream implementation ../../.agents/skills/structure-planning/SKILL.md exposes this workflow as a runtime skill
downstream design html-output.md consumes structure contracts for explicit HTML output
@dependency-end
-->

## Purpose

`structure-planning` is the skill for building a structure contract before
writing prose, running an experiment, rendering a report, planning a
presentation/deck, or starting a refactor. It owns the up-front shape of the
work: audience, decision context, first artifact, section or slice order, slide
or storyboard order, source mapping, invalid interpretations, allowed
structural delta, and validation gate.

It does not own raw result storage, experiment execution, report prose, document
drafting, implementation, or domain authority. Use `result-artifact-writeout`
for raw artifacts, `experiment-lifecycle` for run protocol, `report-writing` for
reader-facing prose, `html-output` for explicit browser-readable output,
`html-experiment-report` for experiment-specific HTML evidence planning,
slide production workflow for PPT/deck layout, writing skills for drafts, and
`refactor-loop` for behavior-preserving changes.

## Use When

- A report, experiment plan, Eval output, decision brief, presentation
  storyboard, PPT/deck plan, HTML view, long document, academic document, paper
  draft, or refactor needs a nontrivial structure before execution.
- The first figure, first table, first ponchi-e/concept diagram, first slide,
  first section, experiment slice, or refactor slice must be decided before
  implementation.
- Source evidence must be mapped to sections, slides, visuals, claims, or
  refactor slices so the agent does not invent unsupported structure while
  drafting or editing.
- A generated artifact could be mistaken for policy, classification, merge,
  deletion, ownership, or behavior-change authority.

## Structure Contract

Create this contract before drafting, rendering, running follow-up experiments,
or editing refactor surfaces:

```text
structure_kind=<report|experiment-plan|experiment-report|eval-report|presentation|html-report|document|paper|refactor|other>
audience=<reader-or-reviewer>
decision_context=<decision or action the structure supports>
first_artifact=<figure|table|ponchi-e|concept-diagram|slide|summary-card|section|experiment-slice|refactor-slice> <short name>
first_artifact_question=<one sentence>
visual_plan=<mermaid|table|text-only|html|image|slide|not-applicable> <why this visual shape fits>
source_to_structure_map=<source path/id -> section, slide, visual, claim, experiment slice, or refactor slice>
metric_or_delta_contract=<denominator, directionality, baseline, caveat, allowed structural delta, forbidden semantic delta>
ordered_structure=<ordered headings, slides/storyboard, visuals, experiment slices, or refactor slices>
invalid_interpretations=<claims or changes this structure must not support>
validation_gate=<reviewer, eval, renderer test, layout review, docs check, dependency check, or behavior-preservation test>
```

For compact work this can be a short block in the report, run bundle, or handoff.
For repo-changing work, store it before adding renderer code, draft prose,
experiment scripts, or refactor edits.

## Default Sequence

1. Fix the audience and decision context.
1. Choose the first artifact: figure, table, ponchi-e/concept diagram, slide,
   summary card, first section, experiment slice, or refactor slice.
1. For reader-facing documents, reports, plans, workflow guides, and refactor
   maps, choose Mermaid as the default first visual when the structure includes
   nontrivial process flow, dependencies, ownership, routing, state transitions,
   review gates, or multi-step handoffs. Use `flowchart`, `sequenceDiagram`,
   `stateDiagram-v2`, or `classDiagram` according to the relation being shown.
   Choose `text-only` only when a diagram would duplicate a simple list, and
   record that reason in `visual_plan`.
1. Define the question answered by that first artifact.
1. Map each source artifact to the section, slide, visual, claim, experiment
   slice, or refactor slice it supports.
1. When block order, transition choice, or logic-gap evidence is nontrivial,
   run `agent-canon semantic-index discourse-relations` with the matching
   connective profile and use the JSONL edge output as structure evidence for the ordered
   structure. The tool separates relation primitives from surface phrases, so
   `therefore` / `because` variants can support the same logical relation while
   recording opposite surface order.
1. When a prose graph projection is available, use
   `prose_reasoning_graph.py explain` and `integrate` as advisory evidence for
   section order, paragraph bridges, split/merge candidates, and invalid
   interpretations before drafting or rewriting.
1. Define metric denominator, directionality, baseline, and caveat for reports
   or experiments; define allowed structural delta and forbidden semantic delta
   for refactors.
1. Write the ordered structure in reader, storyboard, or execution order, not raw
   tool-output order.
1. List invalid interpretations explicitly.
1. Select the validation gate before drafting, rendering, running follow-up
   experiments, or editing files.

## Relationships

- `report-writing` calls this skill before drafting reports with nontrivial
  structure, comparison tables, presentation storyboards, ponchi-e/concept
  diagrams, source-to-slide maps, or evaluation/experiment reader guides.
- `html-output` calls this skill before nontrivial page structure, first
  viewport, source-to-section map, or invalid interpretation boundaries.
- `html-experiment-report` calls this skill before the primary figure contract
  and derives the experiment plan from the structure contract.
- `experiment-lifecycle` calls this skill before experiment planning or
  result/report generation when the output needs a reader-facing or rerun-facing
  structure.
- `long-form-writing`, `academic-writing`, and `paper-writing` call this skill
  when section order, claim/evidence layout, figure/table placement, or reader
  path is nontrivial.
- `refactor-loop` calls this skill when file moves, module boundaries, repair
  slices, path mapping, or responsibility maps need a stable shape before
  implementation.
- `result-artifact-writeout` remains responsible for durable raw evidence and
  summary artifact placement.

## Closeout Tokens

Record these in `workflow_monitoring.md`, a run bundle, or the artifact itself:

```text
structure_planning=complete
structure_contract=<path-or-inline>
structure_first_artifact=<name>
structure_visual_plan=<mermaid|table|text-only|html|image|slide|not-applicable>
structure_source_map=<path-or-inline>
discourse_relations=<path|not_required>
structure_invalid_interpretations_recorded=yes
```
