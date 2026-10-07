# change-review

<!--
@dependency-start
contract skill
responsibility Reviews changed contracts, source/generated ownership, and missed retirement.
upstream design ../../documents/design/responsibility-cleanup.md retirement and consumer migration
upstream design ../../documents/conventions/software-engineering-principles.md contract precedence
upstream design ../../documents/runtime/private-feedback-knowledge.md private evidence and Issue route
@dependency-end
-->

## Purpose

Review the actual diff, resulting owning unit, and existing validation evidence.
Use the host's ordinary review capability where available; this owner adds the
AgentCanon-specific source, generated-surface, and retirement boundaries.
Do not repeat generic review instructions or require a second review solely
because this skill was selected.

## Repeated Responsibility Review

Follow reachable callers and effects, including unchanged superseded code.
When paths overlap, start from the most recently incorporated implementation;
compare semantics before consolidating. A missing-deletion finding identifies
the retained owner, obsolete contribution, and necessary consumer migration.
[RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
owns that migration; restoring aliases or wrappers is not the default remedy.

## Cause and Evidence

Derive the repair from the demonstrated cause, not the symptom. Expand through
callers, state/guards, downstream effects, and relevant sibling implementations
only while they can change the owner, repair, or validation. A direct static
proof is sufficient; no cause-receipt schema or fixed investigation checklist
is required. Unreachable branches and checks already guaranteed upstream are
removal candidates, not reasons to add speculative tests.

Check that generated views follow their actual source and that changed consumers
use the retained entrypoint. A test of retired wording is not a behavior contract;
judge regressions against current required guarantees without weakening oracles.
Select language, numerical, or document specialists only for unresolved risk in
that domain. Reuse applicable validation instead of repeating it.

Report concrete findings first, with location, reachable effect, and evidence.
Keep uncertain causes explicit. Route durable unresolved work to the responsible
repository's Issue; a local finding does not require an Issue or additional gate.
