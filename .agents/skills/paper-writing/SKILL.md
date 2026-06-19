---
name: paper-writing
description: Use when drafting a submission paper, thesis chapter, or other paper-style manuscript that needs section contracts, citation-evidence review, notation review, and logic-gap review.
---
<!--
@dependency-start
contract skill
responsibility Documents paper-writing for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable paper structure contracts
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph diagnostics and rewrite handoffs
@dependency-end
-->


# paper-writing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill paper-writing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/paper-writing.md`.
1. Read `agents/workflows/paper-writing-workflow.md`.
1. Read `agents/workflows/academic-writing-workflow.md`.
1. Select this as the DSL-to-prose projection adapter when file/document responsibility is submission paper, thesis chapter, or paper-style manuscript with paper section contracts and citation/evidence review; do not select it by length.
1. Use `$structure-planning` before drafting when section order, first figure/table, claim/evidence layout, source-to-structure map, or invalid interpretations are nontrivial.
1. For paragraph-level claim flow, transition pairs, or logic-gap triage, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile academic-argument` and treat it as advisory discourse evidence before prose drafting.
1. For nontrivial paper prose creation or revision, create or receive a `$prose-reasoning-graph` handoff before drafting; include its claim/evidence gaps, weak transitions, experiment-plan gaps, and split/merge/bridge/reorder operations in the section contract and reviewer handoff.
1. When the prose graph handoff includes `selected_ordering.ordered_anchors`, use that whole-document topological sentence order as the DSL-to-prose input sequence before drafting paper sections or paragraph transitions.
1. Project paper responsibilities into positive prose contracts: state each section role, claim, citation/evidence relation, result claim, limitation, and reviewer handoff directly. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Before writing paper prose, close `fix-now` findings at the DSL/projection stage: revise the section contract, citation/evidence matrix, paragraph claim map, graph-backed rewrite packet, or graph-backed units, rerun graph diagnostics, and only draft prose after the selected profile has no active findings.
1. After projecting DSL/projection state to paper prose, rerun the graph check. If new findings appear only after projection, record `dsl_to_prose_prompt_defect` against this skill's paper prose-generation prompt and repair it before continuing.
1. Fix the paper intent brief, claim contract, section contract, citation/evidence matrix, notation ledger, and paragraph claim map before drafting.
1. Route citation/evidence review, notation review, logic-gap review, and document-flow review as separate review passes before closeout.
