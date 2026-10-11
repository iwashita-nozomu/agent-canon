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

## Procedure

1. Inspect the current diff against the changed contract and the most recently
   incorporated owner. Review the changed code and contract. Before accepting a
   finding, identify why the current implementation exists and what evidence in
   the target could refute it.
2. For an overlap or missing-deletion finding, identify the retained owner and
   obsolete contribution. RC-09 owns retirement; an alias or wrapper is not the
   default repair.
3. Derive findings from reachable effects and current guarantees, not symptoms or
   reviewer wording. Treat a reviewer result as a hypothesis until source or a
   direct static proof supports it. Unreachable branches and upstream-guaranteed
   checks are deletion candidates, not speculative test triggers.
4. Check generated views against their source. Reuse applicable validation;
   select a language, numerical, or
   document specialist only for unresolved risk in that changed surface.
5. Report concrete findings with location, reachable effect, and evidence. Keep
   uncertain causes explicit and route durable unresolved work to its owner; a
   local finding alone creates no extra Issue or gate.
