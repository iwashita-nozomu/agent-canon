# mvp-skeleton
<!--
@dependency-start
contract skill
responsibility Documents MVP skeleton discipline for skeletal app, site, tool, and product scaffolds.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
downstream implementation ../../.codex/personal/skills/mvp-skeleton/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

Use for an explicitly requested MVP, prototype, runnable vertical slice,
product skeleton, or v0. Deliver the paths and outcomes the user requested.

## MVP Contract

Before editing, establish the intended users, required input-to-output paths
and observable acceptance. Include failure recovery and cleanup where the
requested paths require them. Implement the required behavior through its real
entrypoints and verify acceptance across those paths.

## Frontend Rule

Make the entry screen the usable product surface. Use a landing page only when
the user explicitly asked for a landing page.

For browser UI, use [UI design basis](html-output.md#ui-design-basis) and
[UI information design](html-output.md#ui-information-design) for visual reuse,
layout, necessary copy, and entry-path checks.

Use existing design system pieces and controls that the core loop requires. If
visual assets are required, use a domain-relevant asset that makes the surface
understandable; keep asset work tied to that supporting role.

## Closeout

Report which requested paths are runnable and what the acceptance checks
established. Include the command, URL, or file needed to use the result.
