---
name: academic-writing
description: Use when drafting a paper, thesis chapter, scholarly note, or other academic document that needs mandatory multi-agent review for notation, logic, and reader flow.
---
<!--
@dependency-start
contract skill
responsibility Documents Academic Writing for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/academic-writing.md Academic Writing skill contract
upstream design ../../../agents/skills/structure-planning.md defines reusable document structure contracts
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph diagnostics and rewrite handoffs
upstream environment ../../../CONTAINER_OPERATIONS.md TeX devcontainer tooling boundary
@dependency-end
-->


# Academic Writing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill academic-writing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/academic-writing.md`.
1. Select this as the DSL-to-prose projection adapter when file/document responsibility is academic prose, scholarly note, thesis chapter, method note, or symbol-dense claim-heavy explanation; do not select it by length.
1. Use `$structure-planning` before drafting when section order, figure/table placement, claim/evidence layout, first section, or invalid interpretations are nontrivial.
1. When claim flow or discourse connectives matter, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile academic-argument`; keep TeX routing separate from discourse evidence.
1. For nontrivial academic prose creation or revision, create or receive a `$prose-reasoning-graph` handoff before drafting; use unsupported-claim diagnostics, weak-bridge diagnostics, experiment completeness findings, and split/merge/reorder operations as advisory input to the evidence map, paragraph claim map, and logic-gap review.
1. When the prose graph handoff includes `selected_ordering.ordered_anchors`, use that whole-document topological sentence order as the DSL-to-prose input sequence before drafting academic sections or paragraph transitions.
1. Project academic responsibilities into positive prose contracts: state each claim, definition, warrant, evidence relation, limitation, and reviewer handoff directly. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Before writing academic prose, close `fix-now` findings at the DSL/projection stage: revise the claim contract, evidence map, paragraph claim map, graph-backed rewrite packet, or graph-backed units, rerun graph diagnostics, and only draft prose after the selected profile has no active findings.
1. After projecting DSL/projection state to academic prose, rerun the graph check. If new findings appear only after projection, record `dsl_to_prose_prompt_defect` against this skill's academic prose-generation prompt and repair it before continuing.
1. In Codex, use `/plan` before planning when the runtime provides it, and use `/agent` to inspect available subagents when the runtime provides it.
1. Fix a short `claim contract`: central contribution, gap, reader, and non-goal.
1. Build an `evidence map`, `notation ledger`, and section contract before drafting prose.
1. When the academic artifact needs PDF-ready output, dense math, or figures, create a TeX output plan and use the devcontainer TeX toolchain: `latexmk`, pdfLaTeX, XeLaTeX, `dvisvgm`, and `pdfcrop`.
1. Bootstrap a run bundle and explicitly enable `notation_definition_reviewer` and `logic_gap_reviewer`.
1. Draft in reader order and keep results, interpretation, and limitations separate.
1. For TeX output, keep canonical `.tex` source and validate documents with `latexmk -pdf`; validate figure outputs with `latexmk -pdf` plus `dvisvgm` or `pdfcrop`.
1. Take a reverse outline after drafting.
1. Require `document_flow_reviewer`, a separate `notation_definition_reviewer`, a separate `logic_gap_reviewer`, and a separate reviewer using `docs-completeness-review`.
1. Add `critical-review`, `report-review`, or `docs-consistency-review` when the document warrants them.
1. Do not route general README, workflow, guide, migration, or ordinary report writing to TeX through this skill; TeX is default-wired only for Academic Writing.
