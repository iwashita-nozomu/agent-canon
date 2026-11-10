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

Use the shared [implementation and deletion sequence](../canonical/CODEX_IMPLEMENTATION.md#5-implementation)
from the agreed final behavior, target source, current diff, and most recently
incorporated path. RC-09 owns retirement and necessary caller migration.

- Read control flow in the target and compare existing capabilities before
  adding code. Do not add a compatibility layer as a cleanup step.
- Remove relay-only packets, wrappers, types, and names. Keep abstractions only
   for domain meaning, independent behavior, or a demonstrated shared responsibility.
- For numerical code, establish the governing equations and required invariants.
   When retiring numerical corrections, use [stabilization removal](computational-optimization.md#remove-unsupported-stabilization).
   Use [refactor-loop](refactor-loop.md) for structural migration and
   [change-review](change-review.md) for the resulting contract and missed deletions.

No new inventory, handoff schema, or full-repository scan is required by cleanup.
