# report-writing
<!--
@dependency-start
contract skill
responsibility Documents reader-facing report writing workflow and quality criteria.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design structure-planning.md reusable structure contract skill
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design prose-reasoning-graph.md prose graph diagnostics and handoff overlay
upstream design ../workflows/slide-production-workflow.md slide template, slot, and layout review workflow
downstream design html-output.md consumes report content for explicit HTML rendering and browser publication
downstream design ../../evidence/agent-evals/report_quality_eval.toml report quality checklist eval manifest
downstream implementation ../../.agents/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/evaluate_report_quality.py validates report writing prompt surfaces
@dependency-end
-->

## Reader Map

- Purpose: write reader-facing reports from existing evidence while preserving
  source packets, limitations, quality criteria, and actionability.
- Section path: Purpose and Use When introduce scope; Source Packet and Report
  Quality Checklist define inputs and acceptance; Finding Closure Loop,
  Required Structure, Review Route, Relationship To Other Skills, Closeout
  Tokens, and provenance sections carry operations.
- Use when: status, audit, evaluation, experiment, review, decision, or
  presentation evidence needs human-readable synthesis.
- Boundary: raw result storage stays with `result-artifact-writeout`; nontrivial
  structure is fixed first with `structure-planning` and graph-backed handoff
  when needed.

## Purpose

`report-writing` is the skill for writing reader-facing reports from existing
evidence, including decision briefs, experiment summaries, presentation
narratives, PPT storyboards, and slide-ready visual asset plans. It owns report
prose, claim hygiene, quality review criteria, reader actionability, and
presentation asset traceability. In the common document pipeline, file
responsibility selects this as the DSL-to-prose projection adapter when the
document's job is evidence-backed status, audit, evaluation, review, decision,
recommendation, or presentation narrative. For nontrivial structure, call
`prose-reasoning-graph` and `structure-planning` before prose projection.

Reports can be Markdown or HTML. The default report output is Markdown unless
the user explicitly asks for HTML, a browser page, dashboard, web view, or
external browser publication. When HTML is explicit, use `html-output` after the
source packet and report structure are fixed.
When a deck or PPT is in scope, use the slide production workflow after the
report source packet and presentation asset packet are fixed.

It does not own raw result storage. Use `result-artifact-writeout` for
append-only hook, skill, tool, eval, experiment, and raw machine artifacts, then
use this skill to turn that evidence into a report a human can evaluate.

## Use When

- A user asks for a report, status report, evaluation report, audit report,
  experiment report, review report, decision brief, presentation narrative, PPT
  storyboard, slide asset plan, or improvement guide.
- Tool, hook, skill, eval, experiment, or CI outputs need reader-facing
  synthesis.
- A generated report may influence a workflow, skill, policy, or issue.
- A report needs explicit quality criteria before it is accepted.
- A report needs a first figure/table, presentation storyboard, ponchi-e or
  concept diagram, source-to-section map, source-to-slide map, metric contract,
  or invalid interpretation boundary; in that case use `structure-planning`
  before drafting.
- File / document responsibility classifies the output as a report adapter
  target; in that case create or receive a prose graph handoff, then use graph
  diagnostics, explanation, and integration plan as evidence for reader flow and
  claim support while keeping the report source packet authoritative.
- A report is being written from graph/DSL structure; in that case close
  `fix-now` findings at the DSL/projection stage before projecting to report
  prose.
- A report needs HTML output only when the user explicitly asks for HTML or a
  browser-readable page; in that case use `html-output` after report planning.
- A report is meant for external presentation and therefore needs slide-ready
  visuals, data figures, generated images, figure provenance, reference blocks,
  and layout/preview gates.

## Source Packet

Before drafting, fix these inputs:

- audience: who will read the report
- decision context: what decision or action the report should support
- purpose and non-goals: what the report will and will not settle
- source artifacts: paths, commands, run ids, issue ids, PR ids, commits, or
  logs used as evidence
- observed facts: what the source artifacts directly show
- inferred claims: interpretations derived from the facts
- limitations: missing data, partial runs, stale sources, uncertainty, and
  blocked checks
- next action: concrete follow-up owner, command, PR, issue, or workflow route
- output format: `markdown` by default, `html` when explicitly requested, or
  `deck` / `ppt` when the user asks for slide output
- structure contract: required when the report has a nontrivial reader
  structure; use `structure-planning` to fix first artifact, source-to-section
  map, metric contract, section order, and invalid interpretations
- visual plan: for reports that explain workflow, dependency, ownership,
  routing, state, review gate, handoff, or multi-step evidence flow, use
  `structure-planning` to decide whether the first visual should be a Mermaid
  diagram, table, or text-only outline
- presentation asset needs: required when a deck, PPT, talk, or external
  presentation is in scope; list the core story, first visual, ponchi-e/concept
  diagrams, data-backed figures, generated-image prompts or asset paths, slide
  slot mapping, reference/footnote plan, and layout/preview gate
- DSL/projection closure: required when file responsibility selects this report
  adapter for nontrivial output; revise the structure contract,
  source-to-section map, graph-backed rewrite packet, or graph-backed units and
  rerun graph diagnostics until the selected profile has no active `fix-now`
  findings before writing report prose
- selected ordering: when the prose graph handoff includes
  `selected_ordering.ordered_anchors`, use that whole-document topological
  sentence order as the DSL-to-prose input sequence before drafting report
  sections or paragraph transitions
- positive responsibility prose: state what the report observes, infers,
  recommends, limits, and hands off. Boundary, Limitation, and Non-Goal sections
  hold boundary statements; `ad hoc` labels are replaced with a named
  responsibility, evidence gap, verification route, or prompt-defect
  classification

## Report Quality Checklist

Use this checklist before publishing or handing off a reader-facing report:

- [ ] Audience and decision context are explicit.
- [ ] Purpose and non-goals are explicit.
- [ ] Source artifacts, commands, commits, issues, PRs, or run ids are cited by
  stable path or stable id.
- [ ] Observations are separated from interpretations.
- [ ] Each recommendation or strong claim has evidence, or is labeled as an
  inference.
- [ ] Limitations, uncertainty, missing checks, and stale evidence are called
  out.
- [ ] Provenance includes command, runtime, branch, commit, timestamp, or
  report generator when applicable.
- [ ] The report is actionable: next steps are scoped and assigned to a route,
  owner, command, issue, or PR.
- [ ] Raw artifacts and reader-facing summary paths are not conflated or
  overwritten.
- [ ] For external presentations, the first visual, ponchi-e/concept diagrams,
  data-backed figures, generated images, reference blocks, and slide previews
  are mapped to claims and source artifacts.
- [ ] Conceptual visuals are labeled separately from data-backed figures.
- [ ] The report does not become a second policy truth surface. Any rule change
  is routed to the canonical skill, workflow, tool, document, or issue.
- [ ] Nontrivial process, dependency, ownership, routing, state, review-gate, or
  multi-step evidence flow is shown with a Mermaid diagram, or the source packet
  explains why a table or text-only outline is clearer.

## Finding Closure Loop

When a report has graph diagnostics, reviewer findings, report-quality findings,
or other writing findings, the writing pass is not complete until the selected
finding set is empty. The standard loop is:

For prose graph handoffs, run this loop first at the DSL/projection stage. Do
not spend a prose rewrite pass on a report whose section contract,
source-to-section map, or paragraph bridge is already known to be structurally
invalid.

1. Draft or revise the report from the source packet and structure contract.
1. Run the applicable graph, review, or report-quality checker.
1. Classify each finding as `fix-now`, `out-of-scope`, `tool-false-positive`,
   or `prompt-defect`.
1. Rewrite the responsible section, paragraph, sentence, table, figure caption,
   or equation needed to remove every `fix-now` finding.
1. Rerun the same checker and compare the finding set.

Do not accept a report merely because the loop hit an iteration budget. If the
same finding class persists after repeated targeted rewrites, stop and record a
`prompt-defect` finding against the sentence-generation or section-generation
prompt. The next work item is then prompt repair, not more blind rewriting.

`out-of-scope` and `tool-false-positive` classifications require a short reason
and an artifact path. They are not silent passes. A report may close with those
classifications only when the active task explicitly excludes them or the tool
finding is demonstrably not about the requested report profile.

## Required Structure

Use a structure that fits the report type, but keep these sections explicit:

1. Summary
1. Source Packet
1. Observations
1. Interpretation
1. Limitations
1. Next Actions
1. Report Quality Checklist

For compact reports, these can be short paragraphs or a table. Do not omit the
source packet or limitations only because the report is short.

When `structure-planning` is active, treat its ordered structure as the starting
outline and do not add sections that lack a mapped source, an explicit
inference label, or a stated limitation. If the structure contract records
`discourse_relations=<path>`, use that JSONL as paragraph-order and transition
evidence; do not treat discourse edge scores as source evidence for factual
claims.

When a report uses Mermaid, keep the diagram source in a fenced `mermaid` block
inside the Markdown report or the source artifact that renders the report. The
diagram must have nearby prose that names the question it answers and the
constraints it does not represent.

For external presentations, add a `Presentation Asset Packet` before detailed
results or slide drafting. It must include:

1. Core story and non-goals
1. First visual and its question
1. Required ponchi-e/concept diagrams
1. Required data-backed figures and tables
1. Generated-image prompts or asset paths, when generated images are used
1. Slide/storyboard order and template slot mapping
1. Reference, footnote, and evidence annotation plan
1. Layout/preview gate and artifact manifest path

## Review Route

Use `report_reviewer` when the report is claim-heavy, external-facing,
slide-backed, high-impact, or used as PR / issue / policy evidence. The reviewer
checks:

- structure and reader flow
- source-to-claim traceability
- overclaiming and unsupported recommendations
- missing limitations
- stale or ambiguous evidence paths
- presentation asset traceability and conceptual/data-backed visual separation

For PPT or deck output, also run a layout review so generated images, equations,
references, footnotes, and slide previews remain readable after insertion.

Small internal status notes may record `report_reviewer=not_required` with a
reason.

## Relationship To Other Skills

- `result-artifact-writeout`: owns raw artifact, summary artifact, manifest,
  unique id, and overwrite policy.
- `structure-planning`: owns the pre-draft structure contract, first artifact,
  source-to-section map, metric contract, section order, and invalid
  interpretations.
- `html-output`: owns explicit HTML rendering, layout checks, optional
  `$imagegen` visual assets, and local/external browser server publication.
- `slide-production-workflow`: owns fixed template use, slide slot mapping,
  layout review, reference visibility, and preview evidence for PPT/deck output.
- `long-form-writing`: owns general explanatory prose for README, guide,
  migration, workflow, or specification responsibilities.
- `experiment-lifecycle`: owns experiment run protocol and rerun decisions.
- `change-review`: owns findings-first code or document review output.
- `report-writing`: owns reader-facing synthesis and report quality gates.

## Closeout Tokens

Record these in `workflow_monitoring.md`, a handoff, or the report itself:

```text
report_writing=complete
report_output_format=<markdown|html|deck|ppt>
report_quality_checklist=<pass|fail>
report_source_packet=<path-or-inline>
presentation_asset_packet=<path|inline|not_required>
structure_contract=<path|inline|not_required>
report_reviewer=<path|not_required>
report_rule_drift=<none|canonical_update_required>
```

## Reader Guide For Evaluations And Experiments

Evaluation and experiment reports must include a reader guide before the
detailed table. The guide must state:

- what to inspect first
- each key metric's denominator and directionality
- valid and invalid comparisons
- the main caveat
- what result would change the next action

When the report is presentation-backed, the reader guide must also state which
slide or first visual to inspect first, which visuals are conceptual, which are
data-backed, and what evidence path supports each strong claim.

## External Source Provenance

Reports that use web pages, papers, official docs, or downloaded artifacts must
cite existing durable source notes or create/update source packets before
publishing. Include URL/DOI, access date, claim used, limitation,
adoption/exclusion decision, and artifact location. Browser tabs, download
caches, temporary PDFs, and chat-only summaries are not enough provenance.
