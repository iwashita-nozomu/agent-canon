<!--
@dependency-start
contract skill
responsibility Selects the source evidence and renderer for code and document visualizations.
upstream design ../canonical/skills.md skill canon registry
upstream design dependency-analysis.md dependency graph and function-call evidence
upstream design algorithm-flowchart.md JIT-canonical algorithm and proof-state charts
upstream design structure-refactor.md architecture and responsibility-map evidence
upstream design prose-reasoning-graph.md shared graph projection contract
upstream design html-output.md browser-readable rendering route
downstream implementation ../../.codex/personal/skills/code-visualization/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# code-visualization

## Reader Map

- Purpose: choose a useful view, source-evidence owner, and existing renderer for code, repository, workflow, proof, or document diagrams.
- Section path: Purpose and Context Diagnosis identify the question and scope; Question-To-Diagram Projection selects a view; Source Evidence Routes and Renderer Choice describe execution.
- Use when: a task asks to visualize code, dependencies, runtime behavior, state, data movement, types, proof status, or repository structure.
- Boundary: source facts remain with their owning skills and tools; this skill selects the visualization and renderer without taking their correctness authority.

## Purpose

`code-visualization` classifies what the reader needs to understand, identifies the requested scope and source-evidence owner, and selects an existing visualization and renderer. Source facts are extracted by owners such as `dependency-analysis`, `structure-refactor`, `algorithm-flowchart`, and `prose-reasoning-graph`; the diagram projects those facts.

## Context Diagnosis

Start from the reader's question and requested scope. Identify the existing skill, tool, or artifact that owns the source facts. Consider timing, precision, reader action, and document context only when they change the evidence or representation. If a diagram family is requested, check that it answers the question; add another view only when a requested relation would otherwise remain unclear.

For an embedded diagram, identify the local claim and reader action. Use `structure-planning` when document structure or reader path changes, and `md-style-check` for the changed Markdown properties.

## Question-To-Diagram Projection

| Reader question | Visualization | Typical use | Source owner |
| --- | --- | --- | --- |
| What happens in what order? | Flowchart / activity diagram | Procedures, branches, and execution order | Code owner; `algorithm-flowchart` for JIT/proof overlays |
| Which branches and joins exist? | Control-flow graph | Compiler, static-analysis, or test-design questions | Language analyzer or compiler artifact; `test-design` |
| What calls or imports what? | Call or dependency graph | Function, file, package, or skill relations | `dependency-analysis` |
| Who exchanges messages over time? | Sequence diagram | API, class, or service interactions | Traces, entrypoints, and interface docs |
| How do concurrent events overlap? | Timing or concurrency diagram | Threads, events, async tasks, queues, and races | Trace/log artifacts and runtime contracts |
| What states and transitions exist? | State-transition diagram | Job lifecycle, workflow stages, retries | State definitions and workflow contract |
| Where does data or an artifact move? | Data-flow diagram | Inputs, transforms, stores, outputs | Data schema and I/O owner |
| Which types, protocols, or owners relate? | Type or architecture map | Interfaces and responsibility boundaries | Language-specific owner; `structure-refactor` |
| Where does proof or algorithm status sit? | Algorithm/proof overlay | Implemented operations and theorem status | `algorithm-flowchart` |
| Which large graph needs navigation? | HTML graph or dashboard | Filtering and inspection when requested | `html-output` after source graph exists |

When several questions are present, choose the smallest set of views that answers them. Use reader action and the requested relations to select representation; source-fact authority remains with the producing owner.

## Document Embedded Diagrams

Use this skill when a diagram is embedded in Markdown, reports, design docs, README, workflow or skill docs, or a `visual_plan`. Pair it with `structure-planning` when document structure or reader path changes; use `md-style-check` for relevant Markdown, Mermaid, link, and heading checks.

For an embedded diagram, identify the section claim, the reader's next decision, the source-fact owner, and whether the visual is primary or supporting.

## Source Evidence Routes

For repository dependency diagrams, use the existing native `render_dependency_manifest_graph.py` route. Supply `--graph-tsv` when using an existing checker TSV; otherwise preserve the tool's default checker input. Choose the requested full or changed scope and output flags, and retain the existing `--fail-on-broken` and nonzero checker behavior. The renderer documentation describes its native inputs, GraphIR, manifest, and output formats.

For other diagrams, route source extraction through its owner: `dependency-analysis` for dependency and call relations, `structure-refactor` for architecture and responsibility maps, `algorithm-flowchart` for algorithm/proof views, and `prose-reasoning-graph` for prose graphs. Use `html-output` for browser-readable large graphs and `md-style-check` for embedded Markdown diagrams.

See [the renderer documentation](../../documents/tools/render_dependency_manifest_graph.md) for the current command interface. When a handoff is needed, communicate the question, scope, source owner/artifact, native renderer input, and requested output; do not create a fixed packet or wrapper.

## Renderer Choice

- Mermaid suits compact Markdown flowcharts, sequence, state, type, and data-flow diagrams.
- DOT / Graphviz suits dense dependency or call graphs when layout stability matters.
- HTML dashboards suit requested browser interaction, filtering, or navigation.
- Notebook visualization is selected for experiment results from their existing run artifacts.
- JIT-canonical algorithm diagrams use `algorithm-flowchart` and its current IR, Lean, and theorem-graph evidence route.

The source producer owns factual correctness. The renderer owns syntax and layout. Check the requested output with the existing renderer/formatter route; do not introduce a second source-fact or completeness protocol.

## Closeout

Report the source evidence and owner, the selected renderer and native input, the final artifact or embedding location, and the checks required by that output. Distinguish source validation from rendering/readback.

## Boundaries

- Resolve the reader's question and requested scope before choosing a view.
- Route source facts through their existing owner; a diagram does not replace code, dependency, proof, or runtime correctness checks.
- Use only the existing renderer, native inputs, and output checks for the selected artifact. Add another view only when it answers a requested relation.
