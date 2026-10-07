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

- Start from the agreed final behavior and the most recently incorporated path.
  Read the actual control flow; compare existing capabilities before adding code.
- Follow callers and effects through [dependency-analysis](dependency-analysis.md)
  where the cause or migration boundary remains unresolved. Reuse settled evidence.
- Remove superseded entrypoints, implementation, exclusive dependencies, fixtures,
  and documentation together; migrate necessary consumers to the retained owner.
  [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
  owns retirement details, not an additional compatibility layer or approval gate.
- Remove intermediate concepts as well as their code: packets, wrappers, types,
  and names that merely relay existing data or rename an operation need no separate
  owner. Connect callers directly to the existing responsibility; renaming or moving
  an unnecessary layer is not cleanup. Keep abstractions for actual domain meaning,
  independent behavior, or a demonstrated shared responsibility, not naming alone.
- For numerical code, establish equations and convergence semantics before
  deletion; do not substitute an architecture or JIT change for a mathematical fix.
- Use [refactor-loop](refactor-loop.md) for an actual structural migration and
  [change-review](change-review.md) for the resulting contract and missed deletions.
  Validate changed guarantees and connections, not the retired implementation.

Use existing dependency and reference tools only for unresolved questions.
No new inventory, handoff schema, or full-repository scan is required by cleanup.
