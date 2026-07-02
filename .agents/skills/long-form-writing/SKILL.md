---
name: long-form-writing
description: Use as the general explanatory-doc DSL-to-prose adapter for README, workflow, guide, migration, or specification documents whose file responsibility is reader-facing explanation; do not select this skill by text length alone.
---
<!--
@dependency-start
contract skill
responsibility Documents Long-Form Writing for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines reusable document structure contracts
upstream design ../../../agents/skills/prose-reasoning-graph.md defines prose graph diagnostics and rewrite handoffs
upstream design ../../../agents/skills/formal-proof-workflow.md defines mathematical claim proof-obligation routing
@dependency-end
-->


# Long-Form Writing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill long-form-writing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/long-form-writing.md`.
1. Treat the skill name as compatibility wording. Select this skill by file/document responsibility, not by word count: it is the prose projection adapter for general explanatory repository documents such as README, workflow, guide, migration, and specification docs.
1. If the document is a paper, thesis chapter, scholarly note, or symbol-dense academic manuscript, switch to `academic-writing` instead.
1. Before substantive document additions or revisions, classify whether section order, responsibility, claim/support, reader path, source map, or canonical route changes. If yes, run the structure-analysis gate before adding prose; if the edit is typo/link/format-only, record that reason and use `$md-style-check` instead.
1. For typo/link/format-only handoff to `$md-style-check`, do not require
   runtime `SKILL.md` reading before existing docs tools or patching. Keep
   owner, existing-tool route, and targeted-validation evidence.
1. Use `$structure-planning` when section order, reader path, source mapping, first section, or invalid interpretations are nontrivial; use the structure contract before writing prose.
1. When the document explains workflow, dependency, ownership, routing, state transition, review gate, handoff, or other multi-step flow, ask `$structure-planning` for a `visual_plan` and use Mermaid as the default first visual unless it would duplicate a simple list.
1. When paragraph flow or transition choice is part of that structure decision, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile general` or `--profile academic-argument` before drafting.
1. For nontrivial or substantive creation or revision of a general explanatory document, create or receive a `$prose-reasoning-graph` handoff before drafting reader-facing prose; for an existing repository Markdown document, use `check-document` so prose diagnostics and document-canon diagnostics are generated together.
1. Use prose graph diagnostics, explanation, and integration plan as advisory evidence for section order, paragraph bridges, and split/merge operations.
1. For document split, merge, inline, rename, or keep decisions, use `$structure-planning` to set `document_split_decision` before drafting. Keep content in the same document when owner, reader path, source map, validation route, and update cadence are shared. Do not split for length, token budget, chunking convenience, nearby path, temporary work queue, or shared validation oracle.
1. When the `$prose-reasoning-graph` handoff includes `selected_ordering.ordered_anchors`, use that whole-document topological sentence order as the DSL-to-prose input sequence before drafting sections or paragraphs.
1. Project graph responsibilities into positive prose contracts: state what each section, tool, workflow, or document owns and what evidence supports it. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Decompose each mathematical claim into claim, assumptions, definitions, theorem target or proof obligation, `proof_status`, and checker evidence; route it to `$formal-proof-workflow` before projecting it into reader-facing prose when the claim is proof-like or implementation-derived. For implementation-derived claims, fix a `program contract` first: public entrypoint, input schema, runtime profile, return projection, observable effect, assumptions / preconditions, and validation command. Keep provisional wording as run-local planning evidence, and project canonical text through scope, acceptance conditions, limitations, or validation routes.
1. Before writing reader-facing prose, close `fix-now` findings at the DSL/projection stage: revise the structure contract or graph-backed rewrite packet, add/remove/reorder graph-backed units, rerun graph diagnostics, and only draft prose after the selected profile has no active findings.
1. After projecting DSL/projection state to prose, rerun the graph check. If new findings appear only after projection, record `dsl_to_prose_prompt_defect` against this skill's prose-generation prompt and repair that prompt before continuing.
1. Fix a short summary statement before drafting: main point, purpose, and intended reader.
1. Build a roadmap and section contract before filling in prose.
1. Keep Mermaid diagrams as fenced `mermaid` blocks in the Markdown source, with nearby text stating what the diagram answers and what it does not claim.
1. Draft in reader order and keep long documents scannable.
1. Take a reverse outline after drafting.
1. Require `document_flow_reviewer` and a separate reviewer using `docs-completeness-review`.
1. Add `docs-consistency-review` when the draft changes multiple docs, entrypoints, or canonical routes.
