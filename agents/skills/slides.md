# slides
<!--
@dependency-start
contract skill
responsibility Produces presentation decks from a fixed template while keeping claims, equations, images, and references readable.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/codex/codex-configuration-slides.md slide-deck source and layout reference
upstream design ../../documents/contracts/template-bootstrap.md repository bootstrap and canonical runtime views
upstream design ../../documents/experiments/experiment-report-style.md evidence and report style when a deck presents results
upstream design code-visualization.md selected visualization rendering and coverage owner
upstream design structure-planning.md storyboard topology owner when a real structural choice exists
downstream implementation ../../.codex/personal/skills/slides/SKILL.md exposes this skill as a runtime skill
downstream implementation ../../eval/definitions/skill_workflow_prompt_eval.toml evaluates skill routing coverage
@dependency-end
-->

## Reader Map

- Purpose: keeps a presentation deck's template, slide slots, claims, and
  references aligned through drafting, layout review, and closeout.
- Use When: authoring or revising a slide deck, presentation draft, or Markdown
  deck that is intended to become a presentation asset.
- Section path: Purpose, Activation, Source Packet, and Slot Contract establish
  scope; Workflow and Closeout define the operating route.
- Boundary: this skill owns deck production and layout evidence. Report claims,
  experiment execution, raw results, HTML output, and visualization rendering
  remain with their owning skills.

## Purpose

Use one canonical presentation template and a small slot contract so that text,
equations, generated images, and references remain readable after export. A
deck is accepted from the rendered artifact and its layout evidence, not from
the source text alone.

## Activation

Select this skill when a presentation, slide deck, PPT/PPTX artifact, or
presentation-oriented Markdown deck is explicitly requested. A report does not
become a slide task merely because it contains figures. Activate
`structure-planning` only when slide order, storyboard topology, or reader-state
has a genuine unresolved choice.

## Required Source Packet

Before drafting, read the source that applies:

- `documents/codex/codex-configuration-slides.md`
- `documents/contracts/template-bootstrap.md`
- `documents/experiments/experiment-report-style.md` when the deck presents
  evidence or comparative results

Record the selected template path and any active source artifact paths in the
run bundle. Do not use a blank canvas when a canonical template is available.

## Slot Contract

Map each slide to the slots it actually needs:

- `Title`
- `Body text`
- `Equation`
- `Generated image`
- `Reference block`
- `Footnotes / evidence`

Keep prose in the template and place equations or figures close to the claim
they support. Do not add an unused slot solely to satisfy this list.

## Workflow

1. Lock one canonical template and record its path before writing slide content
   or making layout decisions. Change it only when layout review finds a
   concrete failure that the current template cannot resolve.
1. Define the slide order and the slots each slide uses.
1. Draft in slot order, keeping claim, equation, figure, and reference
   placement explicit.
1. Review the rendered deck for overlap, clipping, tiny text, inconsistent
   spacing, theme drift, unreadable equations, and hidden references.
1. Re-review after inserting or changing a generated image, equation, or other
   non-trivial layout element.
1. Save the deck path, template path, and selected review result in the run
   bundle. Keep one screenshot or exported preview for slides with non-trivial
   layout.

For selected diagrams, hand the complete source facts and rendering call to
`code-visualization`; this skill places the returned projection but does not
reimplement visualization coverage or omission policy.

## Closeout

This skill owns the rendered deck's layout, reference, equation, and image
readability closeout. Read back the rendered deck and the evidence actually
selected for it:

- the fixed template path;
- the source packet used for the deck and its correspondence to the rendered
  artifact;
- slide-to-slot mapping;
- layout review result;
- post-insertion equation/image checks; and
- readable reference placement.

When a reader-facing cumulative report is needed, delegate its production to
`report-writing`; this skill does not reimplement report generation or archive
operations. The report, rendered deck, and source packet must retain explicit
cross-references so that the report describes the artifact that was actually
reviewed.

Do not close while material layout drift, unreadable equations, or hidden
references remain. Do not require screenshots for a deck with no non-trivial
layout, and do not create placeholder evidence for unused operations.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to
this canonical owner.

1. Read `agents/skills/slides.md`.
1. Select this skill only for an explicitly requested presentation artifact;
   reports, HTML, experiments, and visualization rendering keep their owning
   skill unless deck production is also requested.
1. Read the applicable source packet before drafting and record the selected
   template path.
1. Use `structure-planning` only for a genuine storyboard or reader-state
   decision, and use `code-visualization` for selected diagram rendering and
   coverage.
1. Lock the template before drafting and map each slide to the slots it uses.
1. Review the rendered result for layout drift, equation readability, image
   fit, reference visibility, and theme consistency.
1. Re-review after a non-trivial image or equation insertion.
1. Keep deck, template, and selected review evidence in the run bundle and
   read back the rendered artifact at closeout.
