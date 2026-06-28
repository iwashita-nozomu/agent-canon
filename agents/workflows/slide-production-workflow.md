<!--
@dependency-start
contract workflow
responsibility Documents slide production workflow for this repository.
upstream design ../../documents/codex-configuration-slides.md slide deck source reference
upstream design ../../documents/template-bootstrap.md repo bootstrap and canonical runtime views
upstream design ../../documents/experiment-report-style.md document quality and evidence discipline
downstream implementation ../../evidence/agent-evals/skill_workflow_prompt_eval.toml workflow prompt eval coverage
@dependency-end
-->

# Slide Production Workflow

This workflow standardizes slide production on a fixed PPT template so that
text, equations, generated images, and references stay aligned across runs.
Use it when the task is to author or revise a slide deck, presentation draft,
or markdown deck that is intended to become a presentation asset.

## Reader Map

This workflow owns slide-deck production when a fixed presentation template is
part of the task. Read `Scope` to confirm the template and layout boundary,
`Required Source Packet` before drafting, `Workflow` for the slot-based order,
and `Gates` plus `Closeout Checklist` before accepting the deck. It does not
define general report writing or experiment interpretation; those stay with the
source packet and reporting workflows.

## Scope

- Choose one canonical PPT template at task start.
- Keep that template fixed for the whole run.
- `lock the template` before drafting and do not swap it mid-run.
- Map every slide to a small slot set instead of free-form canvas editing.
- Perform a `layout review` before closeout so `reference visibility` does not
  drift.

## Required Source Packet

Before drafting, read:

- `documents/codex-configuration-slides.md`
- `documents/template-bootstrap.md`
- `documents/experiment-report-style.md` when the deck carries evidence or
  comparative results

If the deck is being produced inside a larger repo task, also read the active
goal packet and the run-bundle `goal_work_breakdown.md`.

## Workflow

1. Lock the template.
   - Record the template path in the run bundle.
   - Do not change the template mid-run unless the review gate rejects it.
1. Define slide slots.
   - `Title`
   - `Body text`
   - `Equation`
   - `Generated image`
   - `Reference block`
   - `Footnotes / evidence`
1. Draft in slot order.
   - Put prose in the template, not on an open canvas.
   - Keep equations and figures close to the claim they support.
1. Review for layout drift.
   - Check for overlap, clipping, tiny text, inconsistent spacing, and mixed
     theme styles.
   - Verify that citations and references stay visible and readable.
1. Revise and re-review.
   - If the deck uses generated images, confirm the image still fits the
     slot after insertion.
   - If the slide uses equations, confirm the equation is still legible after
     export.
1. Record evidence.
   - Save the deck path, template path, and review result in the run bundle.
   - Keep at least one screenshot or exported preview for any slide with a
     non-trivial layout.

## Gates

- Do not start from an unbounded blank slide stack when a canonical template
  exists.
- Do not change the template after review has started unless the layout gate
  fails.
- Do not accept a deck that still has layout drift, unreadable equations, or
  hidden references.
- Do not close the task until the deck evidence is written to the run bundle
  and the `closeout checklist` is complete.

## Closeout Checklist

- Template path is fixed and recorded.
- All slides are mapped to slots.
- Layout review passed.
- Generated images and equations were checked after insertion.
- References are readable and placed consistently.
- Evidence is recorded in the run bundle and cumulative report.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py`
and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps slide workflow
rules, prompt routing hooks, and documentation gates mechanically checked
instead of relying on prompt memory.
