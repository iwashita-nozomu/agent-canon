# mvp-skeleton
<!--
@dependency-start
responsibility Documents MVP skeleton discipline for first-pass app, site, tool, and product scaffolds.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
downstream implementation ../../.agents/skills/mvp-skeleton/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

`mvp-skeleton` prevents first-pass MVP work from turning into a polished
product build. It owns the initial scope line: one core user, one core loop, one
runnable path, one smoke check, and an explicit deferred list.

It does not own product strategy, growth planning, production hardening,
architecture design, visual polish, deployment, or comprehensive test strategy.
Use it before implementation when the request is about an MVP, prototype,
first working version, v0, product skeleton, or thin vertical slice.

## MVP Contract

Before editing, fix this compact contract:

```text
core_user=<who needs the first version>
core_loop=<one input-to-useful-output path>
success_signal=<smallest observable result that proves the loop>
runtime_floor=<cheapest local run or inspection path>
stop_line=<tempting work that must be deferred>
```

If the core loop cannot be inferred from the request or repo context, ask one
concise question. Otherwise make a conservative assumption and continue.

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

- a second workflow before the first one runs
- dashboards, settings, onboarding, roles, permissions, billing,
  notifications, search, filters, exports, imports, or analytics
- database schema, backend API, auth, queues, caching, deployment config, or
  persistence not required by the core loop
- reusable component systems, generic services, factories, registries, plugin
  points, or broad abstractions
- elaborate empty states, marketing sections, decorative animation, asset
  libraries, theme systems, or extensive responsive variants
- tests for deferred behavior instead of one smoke check for the MVP path

## Frontend Rule

Make the first screen the usable product surface, not a landing page, unless the
user explicitly asked for a landing page.

Use existing design system pieces and the fewest controls needed for the core
loop. If visual assets are required, use the smallest domain-relevant asset that
makes the surface understandable; do not build an asset system.

## Closeout

Report these items:

```text
mvp_skeleton=complete
mvp_core_loop=<one sentence>
mvp_runtime_floor=<command, URL, or file path>
mvp_smoke_check=<command or manual check>
mvp_deferred=<up to five items>
```

Do not describe deferred items as defects. Deferral is the control mechanism
that keeps the MVP skeletal.
