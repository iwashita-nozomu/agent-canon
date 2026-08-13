# report-writing
<!--
@dependency-start
contract skill
responsibility Writes evidence-backed reader-facing reports with semantic claim/evidence, inference, limitation, and action boundaries.
upstream design ../../documents/design/responsibility-rationale.md report semantics and finding-closure rationale
upstream design structure-planning.md optional structural-decision owner
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.agents/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/evaluate_report_quality.py validates report prompt surfaces
downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

`report-writing` turns existing evidence into reader-facing status, audit, evaluation, experiment, review, decision, recommendation, or presentation prose. Correctness is semantic: material claims map to evidence, observations are separated from inference, material limitations are visible, and the reader can determine the next action.

The canonical rationale is `documents/design/responsibility-rationale.md`. Raw artifacts remain owned by `result-artifact-writeout`. A structure plan is optional and activates only when `structure-planning` identifies a genuine structural decision.

## Source packet

Before drafting, identify the audience/decision, the source artifacts or stable IDs, directly observed facts, inferred claims, material limitations/uncertainty, and the requested next action. Add provenance needed to interpret the evidence. Do not create placeholder fields for evidence classes that do not apply.

When external references support a material claim, use an existing durable source
note or create a source packet with the URL/DOI, access date, source identity,
and adoption/exclusion decision. A browser tab, temporary download, or chat-only
summary is not provenance. For evaluation or experiment reports, add a reader guide that states the denominator, metric directionality, valid and invalid
comparisons, and what result would change the next action.

## Semantic acceptance

A report is acceptable when:

- every material factual or recommendation claim has source support or is explicitly identified as inference;
- observations and interpretations are distinguishable;
- limitations that could change the reader's decision are present;
- raw evidence and reader synthesis are not conflated;
- the next action or conclusion is scoped to what the evidence supports;
- the report does not become a second policy/source-of-truth surface.

No fixed heading count is required. A compact status may satisfy these obligations in a few paragraphs or a small table. External/audit/presentation reports may select more structure when the reader contract requires it. `Report Quality Checklist` is an authoring/review aid, not a mandatory body section.

## Finding closure

Close accepted blocking findings before finalizing. A finding is blocking when it identifies a material factual error, unsupported claim, broken source mapping, or other defect that can change the reader's interpretation or action.

Style/advisory findings, demonstrated tool false positives, explicitly out-of-scope findings, and accepted risks may remain with a short reason. Completion is **not** raw `finding_count == 0`; do not rewrite indefinitely to appease an advisory checker. Rerun only the checker/review surface affected by a changed claim or section.

## Structure and visuals

Do not invoke `structure-planning`, Mermaid, semantic-index, or prose-graph tools merely because a report is nontrivial. Use structure planning only for a real topology decision; use visualization only when it materially improves the reader's understanding. A table or prose is valid without a `text-only` receipt. Selected diagrams delegate rendering/coverage/readback to `code-visualization`.

## Output formats

Markdown is the default reader-facing format. Use `html-output` only when HTML/browser output is explicitly requested. Use the slide-production workflow for requested deck/PPT artifacts. Neither HTML serving nor slide production is implied by writing a report.

## Review route

Use a report reviewer when claim impact, external publication, ambiguity, or evidence complexity warrants independent review. Small internal status reports may complete with direct source-backed review; no `not_required` token is necessary.

## Completion evidence

Read back the report artifact plus the evidence actually selected for it: source packet/provenance, material limitations, selected review result, and any explicitly requested presentation/HTML validation. Do not require fixed seven-section structure or fixed optional closeout fields.
