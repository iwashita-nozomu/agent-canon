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

Before prose, establish slide order, each slide's takeaway, supporting evidence,
and useful visual form through [Before prose](structure-planning.md#before-prose).
Reuse a sufficient outline; a new deck needs this preparation even when its
order is obvious. A bounded edit can retain the existing structure.

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
