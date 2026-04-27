---
name: academic-writing
description: Use when drafting a paper, thesis chapter, scholarly note, or other academic document that needs mandatory multi-agent review for notation, logic, and reader flow.
---
<!--
@dependency-start
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Academic Writing

1. Read `agents/skills/academic-writing.md`.
1. In Codex, use `/plan` before planning when the runtime provides it, and use `/agent` to inspect available subagents when the runtime provides it.
1. Fix a short `claim contract`: central contribution, gap, reader, and non-goal.
1. Build an `evidence map`, `notation ledger`, and section contract before drafting prose.
1. Bootstrap a run bundle and explicitly enable `notation_definition_reviewer` and `logic_gap_reviewer`.
1. Draft in reader order and keep results, interpretation, and limitations separate.
1. Take a reverse outline after drafting.
1. Require `document_flow_reviewer`, a separate `notation_definition_reviewer`, a separate `logic_gap_reviewer`, and a separate reviewer using `docs-completeness-review`.
1. Add `critical-review`, `report-review`, or `docs-consistency-review` when the document warrants them.
