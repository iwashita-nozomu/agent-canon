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

## Reader Map

- Purpose: keeps MVP, prototype, skeleton, or thin-slice work runnable without
  overbuilding architecture, UI, tests, or features while delivering a complete
  final product scope.
- Use When: the request asks for MVP作成, prototype, core runnable path,
  or scope-creep control.
- Section path: Purpose and MVP Contract define the contract; Scope Sort,
  Overbuild Tripwires, and Frontend Rule are operational rules; Closeout states
  completion evidence.
- Boundary: MVP scope is a routing and sequencing control, not permission to
  leave the selected final product scope incomplete or the core path unrunnable.

## Purpose

`mvp-skeleton` defines an MVP or prototype as the smallest complete final product
scope. Establish one core user, one core loop, one runnable path, and an
observable acceptance check. Define failure recovery or cleanup when the path
has a reachable failure or creates state that needs cleanup. A smaller scope is
valid when it is explicitly selected and complete; waves may sequence the
complete target state, but no wave is a completed first implementation.

Route product strategy, growth planning, production hardening, architecture
design, visual polish, deployment, and comprehensive test strategy to their
own skills. Use this skill before implementation when the request is about an
MVP, prototype, runnable vertical slice, v0, product skeleton, or thin vertical
slice.

## MVP Contract

Before editing, establish the core user, input-to-useful-output path, a run or
smoke check that exercises it, and observable acceptance. State a scope boundary
when a plausible addition could change the selected work. Include failure
recovery and cleanup when the selected path makes them relevant. Carry these
decisions in the existing task context; no fixed field list or separate packet
is needed.

When the core loop is unclear from the request or repo context, ask one concise
question. Otherwise make a conservative assumption and continue.

## Scope Sort

Build the selected core loop and any explicitly requested scope. Classify a
candidate only when its inclusion could change the core path or acceptance;
leave unrelated possibilities unlisted. Keep unrequested additions out of the
selected scope unless they are needed to complete that path.

## Overbuild Tripwires

Before adding an unrequested capability beyond the selected loop, check whether
it is needed for the user's scope or acceptance. Common additions include:

- extra workflows before the core loop runs
- dashboards, settings, onboarding, roles, permissions, billing,
  notifications, search, filters, exports, imports, or analytics
- database schema, backend API, auth, queues, caching, deployment config, or
  persistence outside the core loop
- reusable component systems, generic services, factories, registries, plugin
  points, or broad abstractions
- elaborate empty states, marketing sections, decorative animation, asset
  libraries, theme systems, or extensive responsive variants
- a stub class, placeholder, hard-coded replacement, or no-op integration for
  required behavior
- deferring required failure handling, cleanup, or acceptance
- tests for excluded behavior instead of one smoke check for the MVP path

Implement requested or required behavior through its real path; omit other
additions without treating them as future commitments.

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

Report whether the selected path is runnable and its acceptance check result.
Include a command, URL, or file locator when the delivered outcome does not make
clear how to reach or run it. State a scope boundary or unresolved
failure/cleanup only when it affects the expected outcome. Describe out-of-scope
work as excluded from the selected product scope, not as a promise of later
completion.
