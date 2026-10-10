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

Clean the complete owning responsibility, including affected consumers and
obsolete support, rather than choosing a minimum diff or deleting whole files
without understanding their contents.

## Route

1. Start from the agreed final behavior and most recently incorporated path. Read
   actual control flow and compare existing capabilities before adding code.
2. Follow callers and effects through [dependency-analysis](dependency-analysis.md)
   only while the cause or migration boundary remains unresolved.
3. Retire superseded entrypoints, implementation, exclusive support, fixtures, and
   docs together, migrating necessary consumers to the retained owner. RC-09 owns
   retirement; do not add a compatibility layer as a cleanup step.
4. Remove relay-only packets, wrappers, types, and names. Keep abstractions only
   for domain meaning, independent behavior, or a demonstrated shared responsibility.
5. For numerical code, establish equations and convergence semantics before
   deletion. Use [refactor-loop](refactor-loop.md) for structural migration and
   [change-review](change-review.md) for the resulting contract and missed deletions.
6. Validate changed guarantees and consumer connections, not the retired path.

Use existing dependency and reference tools only for unresolved questions.
No new inventory, handoff schema, or full-repository scan is required by cleanup.
