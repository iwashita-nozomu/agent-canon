# html-output
<!--
@dependency-start
contract skill
responsibility Produces and validates browser-readable HTML artifacts; serving/publication is explicit and separate.
upstream design README.md shared skill canon index
upstream design ../../documents/design/responsibility-rationale.md HTML artifact/serving and closeout rationale
upstream design structure-planning.md optional structural-decision owner
upstream design report-writing.md reader-facing report content owner
upstream design code-visualization.md sole public visualization owner and typed projection contract
upstream environment ../../bootstrap/container/image/dependencies.toml supplies the standard Quarto renderer and offline link checker
downstream implementation ../../.codex/personal/skills/html-output/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

`html-output` owns generation and validation of a requested browser-readable HTML artifact: markup, assets, links, layout/readability, accessibility-relevant structure, and any selected rendered visualization. It does not own report claims, experiment execution, raw evidence, or network publication.

## Activation

Use this skill when HTML/browser output is explicitly requested. Reports otherwise default to their normal text/document format. Structure planning activates only if a genuine page-topology decision exists.
For a website build, existing Sites edit, or hosting task that fits the provider,
use the [Sites handoff](README.md#installed-external-skill-handoffs). Pass the
local-only versus deployment condition to Sites; keep already-selected project
edits and standalone HTML with their current owners.

## Artifact validation

Validate the produced file and the properties needed by the request: referenced assets exist, internal links/IDs resolve where applicable, required data/content is present, and selected layout/render checks succeed. Use `code-visualization` for selected graph rendering/coverage.

Check static artifacts directly from their files. For requested browser
interaction checks, use registered `$webapp-testing` with the artifact or
running URL and expected behavior. Accept its observed assertions, screenshots
and console findings here; server lifecycle follows [Preview and serving](#preview-and-serving).

## UI design basis

Before creating or substantially revising a UI, read the relevant project design
guidance, tokens, existing components, and user-specified reference screens.
Reuse them as the visual authority. For a new or substantially restyled UI that
needs a distinct direction, use the [frontend-design handoff](README.md#installed-external-skill-handoffs)
with the brief and constraints. Use the [`$imagegen` route](README.md#official-system-skill-delegation)
for selected raster assets; code-native diagrams and plots stay with their existing renderers. This
Skill retains the project boundary and checks the resulting browser artifact.

Implement the requested surface with existing components. Explain a necessary
departure at the owning design or review location. Preserve brand requirements,
accessible labels, keyboard operation, and reduced-motion behavior.

## UI information design

For UI/control surfaces, make purpose, current state, and next action clear
through hierarchy, placement, grouping, and precise control names. Before adding
repeated captions, obvious helper text, or decorative slogans, fix the layout.
Preserve necessary labels, units, state, errors and recovery, destructive-action
consequences, and accessible names. This applies to interface copy; report
arguments, evidence, and citations keep their content owner's requirements.
Review the actual display or a concrete layout example to check that optional
copy can be removed without losing meaning or accessibility.

Check consistency and layout at the requested display widths. For an added
screen, also follow its intended entry path. For example, a report screen may
wrap correctly at a narrow width while the reports list still has no working
Open report link; those are separate checks. Remove a repeated "This card shows
your report" caption when hierarchy makes it redundant; retain "Sample interval
(ms)" and its validation error beside the input. Record source/layout inspection
and actual browser checks with their respective coverage.

## Standard document rendering

For AgentCanon's document and report route, delegate ordinary Markdown-to-HTML
layout and serialization to the registered native Quarto command. Invoke the
catalog entry `quarto` through `tool run` from the registered project; arguments
after `--` are passed to the native CLI. Do not call Quarto through raw `exec`
or a host installation. Inspect the source, then render it into the external
runtime output directory rather than the read-only project target:

```bash
PROJECT_ROOT=/path/to/registered-project
SOURCE=reports/example.qmd
OUTPUT_DIR=/var/lib/agent-canon/runtime/tool-output
OUTPUT_NAME=report-unique
"$BOOTSTRAP" "${COMMON[@]}" tool run --root "$PROJECT_ROOT" quarto -- \
  inspect "$SOURCE"
"$BOOTSTRAP" "${COMMON[@]}" tool run --root "$PROJECT_ROOT" quarto -- \
  render "$SOURCE" --to html --no-execute \
  --output-dir "$OUTPUT_DIR" --output "${OUTPUT_NAME}.html"
```

Quarto supplies its embedded Pandoc, so do not add a second Markdown parser or
renderer. Code execution, network access, and a serving process remain disabled
unless the request explicitly requires them. Embed resources only when a
single-file artifact is requested, and validate the resulting links/assets with
the existing offline link-check owner. Keep domain facts and specialized
SVG/interactive visualizations with their existing owners.

`BOOTSTRAP` and `COMMON` use the existing
[AgentCanon bootstrap route](agent-canon-bootstrap.md).
`PROJECT_ROOT` is registered with the runtime, `SOURCE` is relative to that root,
and `OUTPUT_NAME` should be unique for the requested artifact.

## Preview and serving

Starting an HTTP server, choosing a port, binding `0.0.0.0`, discovering host addresses, or exposing an external URL are separate delivery operations. Perform them **only** when the user explicitly requests preview, serving, or publication. Use the environment/runtime owner for lifecycle and network rules rather than creating a second server wrapper here.

When serving is requested, start the minimum appropriate process, verify the requested URL/readback, report how to stop it, and do not imply external reachability without evidence.

## Completion evidence

Always read back only:

- artifact identity/path;
- source/provenance needed to interpret it;
- validation actually selected and its result.

Optional operations such as server startup, URL publication, ImageGen, or special policy checks are recorded only when they actually ran. Do not emit `not_requested`, `blocked`, or placeholder fields for unused operations, and do not make fixed token count/field presence an eval oracle.
