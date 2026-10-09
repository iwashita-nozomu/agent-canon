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

Use the requested template, or the applicable canonical template when none is
supplied, with a small slot contract so that text,
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

- [documents/codex/codex-configuration-slides.md](../../documents/codex/codex-configuration-slides.md)
- [documents/contracts/template-bootstrap.md](../../documents/contracts/template-bootstrap.md)
- [documents/experiments/experiment-report-style.md](../../documents/experiments/experiment-report-style.md) when the deck presents
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

Use the requested template when supplied; otherwise select the applicable
canonical template. Record the chosen template when it constrains layout, and
change it only when review finds a concrete failure it cannot resolve. Plan
slide order and use only the slots each slide needs. Keep claims, equations,
figures, and references close enough to show their relationship.

Review the rendered deck for clipping, overlap, text and equation readability,
reference visibility, spacing, and theme consistency. Recheck a slide after a
change that could affect its layout. Keep the deck path, template path, and
relevant review evidence with the deliverable; retain a preview when it helps
resolve or communicate a non-trivial layout question, with no fixed screenshot
count.

For selected diagrams, hand the complete source facts and rendering call to
`code-visualization`; this skill places the returned projection but does not
reimplement visualization coverage or omission policy.

## Closeout

This skill owns the rendered deck's layout, reference, equation, and image
readability. Read back the rendered artifact and the source/template and layout
evidence relevant to the requested deck.

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

1. Read [agents/skills/slides.md](slides.md).
1. Select this skill only for an explicitly requested presentation artifact;
   reports, HTML, experiments, and visualization rendering keep their owning
   skill unless deck production is also requested.
1. Read the applicable source packet before drafting and record the selected
   template path when it constrains the deck.
1. Use `structure-planning` only for a genuine storyboard or reader-state
   decision, and use `code-visualization` for selected diagram rendering and
   coverage.
1. Use the requested or applicable canonical template, and map each slide to
   the slots it uses.
1. Review the rendered result for layout drift, equation readability, image
   fit, reference visibility, and theme consistency.
1. Re-review after a non-trivial image or equation insertion.
1. Keep the deck, applicable template reference, and selected review evidence
   with the deliverable; read back the rendered artifact at closeout.
