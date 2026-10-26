# slides
<!--
@dependency-start
contract skill
responsibility Produces editable presentation decks with a source-backed storyboard and rendered layout review.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/experiments/experiment-report-style.md evidence-bearing presentation style
upstream design code-visualization.md selected diagram rendering owner
upstream design structure-planning.md outline before prose
downstream implementation ../../.codex/personal/skills/slides/SKILL.md runtime discovery adapter
@dependency-end
-->

## Purpose / Activation

Create or revise a requested presentation, including PowerPoint/PPTX and
presentation-oriented Markdown. Deliver the requested format and editability.
Deck production owns the narrative, composition, and layout review; source
claims and experiments retain their existing owners.

## Sources and storyboard

Read the brief, intended audience, presentation setting, source material, and
any supplied deck or template. Reuse relevant figures and assets. Load only the
sources that affect this deck.
For result-bearing decks, follow [experiment report style](../../documents/experiments/experiment-report-style.md)
for evidence, interpretation, limitations, and failures. Keep source deck,
template, and reused figure identities with the authoring inputs.

Set slide order through [structure-planning](structure-planning.md#before-prose).
The [Slot Contract](#slot-contract) owns each slide's takeaway, supporting
evidence, and useful visual form. A bounded edit can retain the existing
structure.

For an existing native Google Slides deck or reference deck, use the
[Google Slides handoff](README.md#installed-external-skill-handoffs). New PPTX
decks use the local authoring route below; selected bitmap assets may use the
[`$imagegen`](README.md#official-system-skill-delegation). Keep image
placement and claim/evidence review with the deck owner.

## Slot Contract

Use the supplied template, or an available canonical presentation template that
fits the request. Otherwise establish a coherent layout from audience needs:
clear hierarchy, aligned grid, restrained typography and color, adequate space,
and consistent visual roles. Use only needed slots for title, body, equations,
figures, references, and evidence.

Give each slide a clear takeaway and group its supporting material. Choose
comparison, sequence, relationship, or quantitative graphics according to the
claim. Put labels, units, sources, and necessary qualifications near the content
they explain; preserve equations and reference readability.

## PowerPoint authoring

Use an available presentation editor or authoring library and its existing
export/render utilities. For existing decks, inspect the original rendering,
masters, aspect ratio, fonts, and objects before editing; preserve unaffected
content and styling. Reuse existing helpers rather than rebuilding layout tools.

With PptxGenJS, choose slide dimensions and theme fonts before adding objects.
Keep text and suitable charts as editable PowerPoint objects, preserve image
aspect ratios, and size text boxes from content. Use the installed helper API
for text/image geometry when available. Retain chart data and formula sources.
Use [code-visualization](code-visualization.md) for selected diagram rendering.

A requested `.pptx` needs an actual PowerPoint file. Retain the authoring source
and required assets so the deck can be rebuilt. For Markdown decks, use their
existing presentation renderer and the requested export format.

## PowerPoint comments

For local PPTX review comments, use the external
[OfficeCLI route](README.md#officecli) when selected and available. Keep narrative
and review acceptance here; CLI behavior and specialized instructions stay with
the provider. Read both legacy comments and modern threads:

```bash
officecli query deck.pptx comment --json
officecli query deck.pptx modernComment --json
officecli get deck.pptx '/slide[1]/modernComment[1]' --depth 1 --json
```

Use paths returned by the query for `get`; the last command illustrates a thread
on slide 1. Modern thread nodes include replies as children and the thread's
`resolved` state; resolution belongs to the parent thread, not individual replies.
Retain slide/path, author, text, replies, and resolution when reporting review
feedback. A legacy-comment query alone cannot establish that all feedback was
read. These commands inspect comments; changing replies or resolution requires
the requested editing scope.

## Layout review and closeout

Render the produced deck and inspect its slides for overflow, overlap, font
substitution, contrast, text/equation readability, image fit, reference visibility,
and consistency. Use existing bounds/font checks where the chosen tool provides
them. Review changed slides again after layout-affecting edits. Preserve review
evidence useful to the request without a fixed screenshot count.

Deliver the deck, required authoring inputs, and actual review results. Missing
rendering or material layout defects remain unverified or unresolved. Link a
requested cumulative report to the reviewed deck through [report-writing](report-writing.md).

## Upstream reuse

PowerPoint guidance adapts [OpenAI's slides skill at e6afb0d](https://raw.githubusercontent.com/openai/skills/e6afb0d74cc75d220df2faf3dd6c635c2dc6a108/skills/.curated/slides/SKILL.md).
Copyright (c) Microsoft Corporation. Licensed under [Apache 2.0](../../LICENSE);
[upstream license](https://raw.githubusercontent.com/openai/skills/e6afb0d74cc75d220df2faf3dd6c635c2dc6a108/skills/.curated/slides/LICENSE.txt).
AgentCanon modifications: provider-neutral routing, conditional helper use,
source/storyboard integration, and shared design and validation ownership.
