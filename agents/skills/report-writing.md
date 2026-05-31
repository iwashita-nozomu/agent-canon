# report-writing
<!--
@dependency-start
responsibility Documents reader-facing report writing workflow and quality criteria.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design structure-planning.md reusable structure contract skill
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design prose-reasoning-graph.md prose graph diagnostics and handoff overlay
downstream design html-output.md consumes report content for explicit HTML rendering and browser publication
downstream design ../evals/report_quality_eval.toml report quality checklist eval manifest
downstream implementation ../../.agents/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/evaluate_report_quality.py validates report writing prompt surfaces
@dependency-end
-->

## Purpose

`report-writing` is the skill for writing reader-facing reports from existing
evidence. It owns report prose, claim hygiene, quality review criteria, and
reader actionability. For nontrivial structure, call `structure-planning` first
and use its structure contract as the report skeleton.

Reports can be Markdown or HTML. The default report output is Markdown unless
the user explicitly asks for HTML, a browser page, dashboard, web view, or
external browser publication. When HTML is explicit, use `html-output` after the
source packet and report structure are fixed.

It does not own raw result storage. Use `result-artifact-writeout` for
append-only hook, skill, tool, eval, experiment, and raw machine artifacts, then
use this skill to turn that evidence into a report a human can evaluate.

## Use When

- A user asks for a report, status report, evaluation report, audit report,
  experiment report, review report, decision brief, or improvement guide.
- Tool, hook, skill, eval, experiment, or CI outputs need reader-facing
  synthesis.
- A generated report may influence a workflow, skill, policy, or issue.
- A report needs explicit quality criteria before it is accepted.
- A report needs a first figure/table, source-to-section map, metric contract,
  or invalid interpretation boundary; in that case use `structure-planning`
  before drafting.
- A report has a prose graph handoff; in that case use the graph diagnostics,
  explanation, and integration plan as evidence for reader flow and claim
  support while keeping the report source packet authoritative.
- A report needs HTML output only when the user explicitly asks for HTML or a
  browser-readable page; in that case use `html-output` after report planning.

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
- output format: `markdown` by default, or `html` only when explicitly requested
- structure contract: required when the report has a nontrivial reader
  structure; use `structure-planning` to fix first artifact, source-to-section
  map, metric contract, section order, and invalid interpretations

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
- [ ] The report does not become a second policy truth surface. Any rule change
  is routed to the canonical skill, workflow, tool, document, or issue.

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

## Review Route

Use `report_reviewer` when the report is claim-heavy, external-facing,
high-impact, or used as PR / issue / policy evidence. The reviewer checks:

- structure and reader flow
- source-to-claim traceability
- overclaiming and unsupported recommendations
- missing limitations
- stale or ambiguous evidence paths

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
- `long-form-writing`: owns long guide, README, migration, or workflow prose.
- `experiment-lifecycle`: owns experiment run protocol and rerun decisions.
- `change-review`: owns findings-first code or document review output.
- `report-writing`: owns reader-facing synthesis and report quality gates.

## Closeout Tokens

Record these in `workflow_monitoring.md`, a handoff, or the report itself:

```text
report_writing=complete
report_output_format=<markdown|html>
report_quality_checklist=<pass|fail>
report_source_packet=<path-or-inline>
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

## External Source Provenance

Reports that use web pages, papers, official docs, or downloaded artifacts must
cite existing durable source notes or create/update source packets before
publishing. Include URL/DOI, access date, claim used, limitation,
adoption/exclusion decision, and artifact location. Browser tabs, download
caches, temporary PDFs, and chat-only summaries are not enough provenance.
