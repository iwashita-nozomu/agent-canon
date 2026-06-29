# mvp-skeleton
<!--
@dependency-start
contract skill
responsibility Documents MVP skeleton discipline for skeletal app, site, tool, and product scaffolds.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
downstream implementation ../../.agents/skills/mvp-skeleton/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: keeps MVP, prototype, skeleton, or thin-slice work runnable without
  overbuilding architecture, UI, tests, or features.
- Use When: the request asks for MVP作成, prototype, core runnable path,
  or scope-creep control.
- Section path: Purpose and MVP Contract define the contract; Scope Sort,
  Overbuild Tripwires, and Frontend Rule are operational rules; Closeout states
  completion evidence.
- Boundary: MVP scope is a routing and sequencing control, not permission to
  leave the core path unrunnable.

## Purpose

`mvp-skeleton` keeps MVP work shaped around a skeletal product slice. It owns
the scope line: one core user, one core loop, one runnable path, one smoke
check, and an explicit deferred list.

Route product strategy, growth planning, production hardening, architecture
design, visual polish, deployment, and comprehensive test strategy to their
own skills. Use this skill before implementation when the request is about an
MVP, prototype, runnable vertical slice, v0, product skeleton, or thin vertical
slice.

## MVP Contract

Before editing, fix this compact contract:

```text
core_user=<who uses the skeletal slice>
core_loop=<one input-to-useful-output path>
success_signal=<observable result that proves the core loop>
runtime_floor=<local run or inspection path that exercises the loop>
stop_line=<tempting work that must be deferred>
```

When the core loop is unclear from the request or repo context, ask one concise
question. Otherwise make a conservative assumption and continue.

## Scope Sort

Classify every candidate item before building it:

| Class | Meaning | Default Action |
| ----- | ------- | -------------- |
| `required` | Removing it breaks the one core loop. | Implement it. |
| `stub` | The loop is understandable with hard-coded data, local state, mock output, a placeholder screen, or a no-op integration. | Stub it. |
| `defer` | The loop still works without it. | Leave it out and report it. |

When classification is unclear, choose `defer`.

## Overbuild Tripwires

Stop and re-scope before adding:

- extra workflows before the core loop runs
- dashboards, settings, onboarding, roles, permissions, billing,
  notifications, search, filters, exports, imports, or analytics
- database schema, backend API, auth, queues, caching, deployment config, or
  persistence outside the core loop
- reusable component systems, generic services, factories, registries, plugin
  points, or broad abstractions
- elaborate empty states, marketing sections, decorative animation, asset
  libraries, theme systems, or extensive responsive variants
- tests for deferred behavior instead of one smoke check for the MVP path

## Frontend Rule

Make the entry screen the usable product surface. Use a landing page only when
the user explicitly asked for a landing page.

Use existing design system pieces and controls that the core loop requires. If
visual assets are required, use a domain-relevant asset that makes the surface
understandable; keep asset work tied to that supporting role.

## Closeout

Report these items:

```text
mvp_skeleton=complete
mvp_core_loop=<one sentence>
mvp_runtime_floor=<command, URL, or file path>
mvp_smoke_check=<command or manual check>
mvp_deferred=<up to five items>
```

Describe deferred items as deliberate scope control. Deferral is the control
mechanism that keeps the MVP skeletal.
