---
name: paper-writing
description: Use when drafting a submission paper, thesis chapter, or other paper-style manuscript that needs section contracts, citation-evidence review, notation review, and logic-gap review.
---
<!--
@dependency-start
responsibility Documents paper-writing for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable paper structure contracts
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph diagnostics and rewrite handoffs
@dependency-end
-->


# paper-writing

1. Read `agents/skills/paper-writing.md`.
1. Read `agents/workflows/paper-writing-workflow.md`.
1. Read `agents/workflows/academic-writing-workflow.md`.
1. Use `$structure-planning` before drafting when section order, first figure/table, claim/evidence layout, source-to-structure map, or invalid interpretations are nontrivial.
1. For paragraph-level claim flow, transition pairs, or logic-gap triage, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile academic-argument` and treat it as advisory discourse evidence before prose drafting.
1. If a prose graph handoff is present, include its claim/evidence gaps, weak transitions, experiment-plan gaps, and split/merge/bridge/reorder operations in the section contract and reviewer handoff.
1. Before writing paper prose from a prose graph handoff, close `fix-now` findings at the DSL/projection stage: revise the section contract, citation/evidence matrix, paragraph claim map, or graph-backed rewrite packet, rerun graph diagnostics, and only draft prose after the selected profile has no active findings.
1. Fix the paper intent brief, claim contract, section contract, citation/evidence matrix, notation ledger, and paragraph claim map before drafting.
1. Route citation/evidence review, notation review, logic-gap review, and document-flow review as separate review passes before closeout.
