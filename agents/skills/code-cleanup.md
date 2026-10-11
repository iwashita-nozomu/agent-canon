# code-cleanup

<!--
@dependency-start
contract skill
responsibility Removes obsolete code and support by owning responsibility and reachability.
upstream design ../../documents/design/responsibility-cleanup.md retirement and consumer migration
upstream design ./dependency-analysis.md unresolved dependency and cause investigation
upstream design ./refactor-loop.md structural migration
upstream design ./change-review.md changed contract review
downstream implementation ../../.codex/personal/skills/code-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
@dependency-end
-->

## Purpose

Clean the requested responsibility from its target source and governing
contract. Keep cleanup within the requested unit.

## Route

1. Start from the agreed final behavior, target source, current diff, and most
   recently incorporated path. Read control flow in the target and compare
   existing capabilities before adding code.
2. Retire superseded entrypoints, implementation, exclusive support, fixtures,
   and docs in the requested unit. RC-09 owns retirement; do not add a
   compatibility layer as a cleanup step.
3. Remove relay-only packets, wrappers, types, and names. Keep abstractions only
   for domain meaning, independent behavior, or a demonstrated shared responsibility.
4. For numerical code, establish equations and convergence semantics before
   deletion. Use [refactor-loop](refactor-loop.md) for structural migration and
   [change-review](change-review.md) for the resulting contract and missed deletions.
5. Validate the changed guarantees in the selected scope.

No new inventory, handoff schema, or full-repository scan is required by cleanup.
