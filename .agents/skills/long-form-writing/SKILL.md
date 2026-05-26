---
name: long-form-writing
description: Use when drafting a long README, workflow, guide, migration doc, or other reader-facing long-form document that needs explicit structure and mandatory subagent review.
---
<!--
@dependency-start
responsibility Documents Long-Form Writing for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable document structure contracts
@dependency-end
-->


# Long-Form Writing

1. Read `agents/skills/long-form-writing.md`.
1. If the document is a paper, thesis chapter, scholarly note, or symbol-dense academic manuscript, switch to `academic-writing` instead.
1. Use `$structure-planning` when section order, reader path, source mapping, first section, or invalid interpretations are nontrivial; use the structure contract before writing prose.
1. When paragraph flow or transition choice is part of that structure decision, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile general` or `--profile academic-argument` before drafting.
1. Fix a short summary statement before drafting: main point, purpose, and intended reader.
1. Build a roadmap and section contract before filling in prose.
1. Draft in reader order and keep long documents scannable.
1. Take a reverse outline after drafting.
1. Require `document_flow_reviewer` and a separate reviewer using `docs-completeness-review`.
1. Add `docs-consistency-review` when the draft changes multiple docs, entrypoints, or canonical routes.
