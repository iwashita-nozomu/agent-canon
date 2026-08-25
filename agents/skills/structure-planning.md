# structure-planning
<!--
@dependency-start
contract skill
responsibility Plans document/artifact topology only when owner, reader, source-of-truth, split/merge, or validation topology is genuinely undecided.
upstream design ../../documents/design/responsibility-rationale.md structure and visualization activation rationale
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/structure-planning/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/task_close.py consumes document_split_decision when a structural decision actually occurs
downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

Use `structure-planning` only when the task contains a real structural decision: a responsibility owner, canonical source, reader entry, document split/merge, section topology, presentation/storyboard topology, or validation route has more than one plausible target. A bounded claim, wording, link, paragraph, or already-owned section edit does not activate this skill merely because it is substantive.

The long-lived reason and activation boundary are owned by `documents/design/responsibility-rationale.md`. This skill owns the selected structural decision; it does not create evidence that an unselected responsibility was skipped.

## Activation

Activate when at least one of these changes:

- owner or canonical source of truth;
- reader entry or downstream consumer;
- document split/merge/rename or section responsibility boundary;
- validation topology or update cadence;
- artifact/storyboard ordering where competing structures affect the reader decision.

Do not activate for typo/link/format fixes, bounded claim/support edits inside an existing owner, ordinary paragraph edits with an already-obvious order, or because an artifact is long or `nontrivial`. Do not emit a `structure_contract=skipped` receipt for those cases.

## Minimal structure decision

Record only facts needed to make the unresolved decision:

```text
structure_kind=<document|report|experiment|presentation|html|refactor|other>
audience=<reader>
decision_context=<decision supported>
owner_and_source=<canonical owner/source>
selected_topology=<ordered units or structural delta>
source_map=<source -> affected unit/claim>
invalid_interpretations=<material forbidden readings>
validation_route=<owner/check>
```

Add a split/merge decision only when a split/merge is in scope. Split on a real owner, reader, source, validation, cadence, or consumer boundary; never split for token budget, length, section count, or temporary work-queue convenience.

## Visualization selection

Choose the first representation by information gain, not by category words. Mermaid is appropriate when state, ownership, dependency, routing, or many-to-many relations are materially clearer as a diagram. Use text or a table without a negative receipt when those forms are already unambiguous. If a diagram is selected, delegate rendering/readback/coverage to `code-visualization`.

## Experiment boundary

An experiment plan always needs hypothesis/input/method/environment/metric/output/reproducibility ownership. Add an OOP responsibility map only when stateful objects, plugin/factory boundaries, mutation ownership, or dependency direction are an actual risk. Pure functions, numerical scripts, and simple benchmarks do not need an invented object model or `not_required` token.

## Prose diagnostics

Semantic-index and prose-reasoning-graph tools are optional diagnostics. Use one only when direct review leaves a concrete ordering or bridge hypothesis unresolved. Do not run both by default, do not make their finding count an acceptance oracle, and do not record a negative token when they are not selected.

## Closeout

For an activated structural decision, read back the selected owner/source, topology, source map, material invalid interpretations, and validation route. Record only fields that participated in the decision. Ordinary bounded edits complete through their owning skill and targeted docs/review checks without a structure packet.

## Relationships

`report-writing`, `html-output`, experiment, slide, and refactor owners may invoke this skill when they encounter a genuine structural choice. They do not invoke it solely because their output class is a report, experiment, HTML artifact, presentation, or refactor.
