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
Repeat a completed review only after new diff, evidence, or a decision-relevant
requirement; Skill selection alone does not require a second review.

## Procedure

1. Compare the actual diff and resulting behavior with changed and retained
   requirements and the owning contract; the latest explicit user instruction
   governs conflicts, while compatible earlier requirements remain active. Use
   implementation rationale and target evidence to assess findings; history
   explains changes but does not define correctness.
2. For overlap or missed retirement, compare reachable behavior across names,
   locations, wrappers, and branches; identify the retained owner and obsolete
   contribution. A rename or move does not retire equivalent behavior. RC-09
   owns retirement; an alias or wrapper is not the default repair.
3. Derive findings from reachable effects and current guarantees, not symptoms
   or reviewer wording; validate reviewer hypotheses against source or direct
   static proof. Unreachable branches and upstream-guaranteed checks are deletion
   candidates, not speculative test triggers.
4. Check generated views against their source. Reuse applicable validation;
   select a language, numerical, or
   document specialist only for unresolved risk in that changed surface.
5. Report concrete findings with location, reachable effect, and evidence. Keep
   uncertain causes explicit and route durable unresolved work to its owner; a
   local finding alone creates no extra Issue or gate.
