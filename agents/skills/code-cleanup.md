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

Clean the requested responsibility from its current source and contract. Include
other files only when the requested retirement or current evidence shows they
are affected; do not survey or edit possible consumers by default.

## Route

1. Start from the agreed final behavior, target source, current diff, and most
   recently incorporated path. Read control flow in the target and compare
   existing capabilities before adding code.
2. Use [dependency-analysis](dependency-analysis.md) for a concrete unresolved
   cause or migration boundary; follow callers and effects only as far as needed
   to settle it.
3. Retire superseded entrypoints, implementation, exclusive support, fixtures, and
   docs together, migrating necessary consumers to the retained owner. RC-09 owns
   retirement; do not add a compatibility layer as a cleanup step.
4. Remove relay-only packets, wrappers, types, and names. Keep abstractions only
   for domain meaning, independent behavior, or a demonstrated shared responsibility.
5. For numerical code, establish equations and convergence semantics before
   deletion. Use [refactor-loop](refactor-loop.md) for structural migration and
   [change-review](change-review.md) for the resulting contract and missed deletions.
6. Validate changed guarantees and only those consumer connections included in
   the requested migration; do not expand validation to possible consumers.

Use existing dependency and reference tools only for unresolved questions.
No new inventory, handoff schema, or full-repository scan is required by cleanup.
