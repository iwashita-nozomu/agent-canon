# change-review
<!--
@dependency-start
contract skill
responsibility Reviews changed code/docs/generated surfaces findings-first and escalates only durable follow-up work.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design ../../documents/design/responsibility-rationale.md durable finding and OOP-review activation rationale
upstream design ../../issues/README.md durable issue and GitHub mirror policy
upstream design ../internal-routines/design-implementation-correspondence.md forward/reverse design correspondence and drift block route
@dependency-end
-->

## Purpose

Review the actual diff and selected validation evidence findings-first. Findings must be grounded in reachable behavior, contract/design drift, or a concrete maintenance/safety failure; broad style preferences are non-blocking guidance.

## Finding model

For each material finding record enough to act on it: affected surface, evidence, impact/severity, and current resolution. Issue lifecycle is independent from finding validity.

Use a durable issue only when the finding outlives the current review: it belongs to another owner/scope, recurs, needs later work, or cannot safely be closed in the current diff. Findings fixed in the current change, questions, rejected hypotheses, duplicates, and accepted local resolutions do **not** need `issue_route`, a local issue file, or a GitHub mirror.

Remote mirror/publication follows the canonical issue policy; review does not perform remote reconciliation merely because a finding exists.

## OOP/SOLID activation

Delegate OOP/SOLID sensitivity to the canonical Python/OOP reviewer. Do not add OOP readability or SOLID evidence just because the changed path contains a class, dataclass, Protocol, annotation, parser model, or public type. Select it when inheritance/substitutability, dependency inversion, responsibility ownership, mutation/lifecycle, DI, or a public object model materially changes.

Do not duplicate a second SOLID-sensitive trigger table in this skill.

## Review order

1. Read base/head and the changed surface.
2. Read the owning contract/design and targeted validation evidence.
3. Report blocking correctness/safety/design findings before summary.
4. Resolve current-scope findings in the current diff when possible.
5. Escalate only durable residual work to the issue owner.
6. State merge/acceptance readiness from unresolved blocking findings and required validation, not from issue-count or packet completeness.

## Boundary

A review does not invent extra gates, tests, reports, or durable lifecycle records merely to make its schema complete. Existing canonical validation and publication owners remain authoritative.
