---
name: code-visualization
description: Sole public visualization owner for code, repository structure, runtime behavior, state, data movement, dependencies, types, proof state, interactive graphs, and document diagrams; builds the complete typed universe and coverage manifest before delegating renderer-only projection.
---

<!--
@dependency-start
contract skill
responsibility Exposes the sole public typed code visualization owner to Codex skill discovery.
upstream design ../../../agents/skills/code-visualization.md canonical skill document
upstream design ../../../agents/skills/dependency-analysis.md dependency and call graph evidence
upstream design ../../../agents/skills/algorithm-flowchart.md JIT/proof flowchart evidence
upstream design ../../../agents/skills/structure-refactor.md architecture and responsibility-map evidence
upstream design ../../../agents/skills/prose-reasoning-graph.md shared graph projection contract
upstream implementation ../../../tools/agent_tools/visualization_contract.py owns the exact D2.4 seven-function API
upstream implementation ../../../tools/agent_tools/route.py emits the singular canonical owner route
@dependency-end
-->

# Code Visualization

## Reader Map

- Purpose: runtime entrypoint for the sole public visualization owner; establish
  complete typed coverage before selecting a diagram or renderer.
- Use When: a task asks to visualize code, dependencies, state transitions,
  architecture, proofs, or document-embedded diagrams.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/code-visualization.md` selection rules.
- Boundary: producer skills/tools retain source-fact authority;
  `code-visualization` owns universe/coverage, and renderer adapters own only
  syntax/layout projection.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill code-visualization --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

## Canonical Contract Gate

Before any renderer selection or command, read and apply
`agents/skills/code-visualization.md` `Canonical Contract And Ownership`.
`code-visualization` is the sole public owner, and
`tools/agent_tools/visualization_contract.py` is the single exact typed module
for `VisualizationSourceUniverse`, `ProjectionCoverageManifest`, canonical
ToolCall validation, coverage/readback digests, and typed rejection statuses.
Use only its seven public functions: `build_source_universe`,
`build_projection_coverage_manifest`, `validate_projection_coverage`,
`serialize_tool_call`, `serialize_projection_identity`,
`serialize_projection_coverage_manifest`, and `readback_projection`. Never call
an underscore-prefixed owner helper.

The fixed ToolID registry is exactly:

- `agent_canon.visualization.coverage` /
  `agent_canon.visualization.arguments.coverage.v1`;
- `agent_canon.visualization.adapter.dependency_manifest` /
  `agent_canon.visualization.arguments.dependency_manifest.v1`;
- `agent_canon.visualization.adapter.algorithm_flowchart` /
  `agent_canon.visualization.arguments.algorithm_flowchart.v1`;
- `agent_canon.visualization.adapter.document_mermaid` /
  `agent_canon.visualization.arguments.document_mermaid.v1`;
- `agent_canon.visualization.adapter.repository_graph` /
  `agent_canon.visualization.arguments.repository_graph.v1`;
- `agent_canon.visualization.adapter.knowledge_graph` /
  `agent_canon.visualization.arguments.knowledge_graph.v1`.

The runtime order is mandatory:

1. Preserve literal user scope and compute complete source-owner and dependency
   closure into one immutable `VisualizationSourceUniverse`.
2. Validate the schema-bearing canonical owner ToolCall with
   `tool_id = agent_canon.visualization.coverage` and
   `argument_schema = agent_canon.visualization.arguments.coverage.v1`.
3. Validate the selected adapter ToolCall after the owner call, serialize every
   locator with `serialize_projection_identity`, and create the complete
   `ProjectionCoverageManifest`.
4. Obtain its marker only from `serialize_projection_coverage_manifest` with
   the owner call first and adapter call second; then render and run the owning
   formatter.
5. After mandatory formatting, run final-artifact readback and return all
   canonical counts, digest, tokens, and typed status.

Universe membership and reversible view-state rules are owned by the canonical
document and must not be redefined here. Diagram family, clustering, zoom,
expansion, and filtering are view-only; every source identity remains serialized
and discoverable. If complete rendering is impossible, return the canonical
typed renderer-capacity blocker instead of pruning or partial fallback.

## Small-Model Direct Route

For repository/code-space dependency visualization, use this self-sufficient
route only after the Canonical Contract Gate. The generated full-scope command
is exact:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json
```

Use `--scope changed` only when the request explicitly asks for changed scope:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json
```

For a supplied TSV path, use the same renderer and bundle with the exact input
flag:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --graph-tsv reports/dependency_graph.tsv --bundle-dir reports/dependency-graph --format json
```

Treat these three commands as immutable flag templates. Copy the selected
command with every shown flag: `--root .` and `--format json` are mandatory in
all three routes. Do not remove, add, or rename any flag. For a supplied TSV,
only the path value after `--graph-tsv` and the path value after `--bundle-dir`
may be replaced with user-provided paths; keep every other token unchanged.

The selected command is a typed adapter ToolCall downstream of the canonical
owner ToolCall. Log both calls in order:

- owner `tool_id = agent_canon.visualization.coverage`
- owner `argument_schema = agent_canon.visualization.arguments.coverage.v1`
- adapter `tool_id = agent_canon.visualization.adapter.dependency_manifest`
- adapter `argument_schema = agent_canon.visualization.arguments.dependency_manifest.v1`
- adapter `arguments` using the exact canonical shared typed fields plus
  `dependency_manifest_locator`

Record the owner call first and the dependency adapter call second. The Python
path and CLI flags in the literal command are execution details, never ToolID
or ToolCall argument-schema substitutes.

`--json` is invalid; use `--format json`.
`check_dependency_graph.sh` owns dependency pass/fail authority. In generated
mode, the renderer invokes that checker for the
generated TSV and owns only Graph IR, Markdown, DOT, HTML, and bundle/manifest
projection creation. For a supplied TSV, checker status is `not_run`: the
supplied TSV producer owns source facts and the renderer owns only projections.
This route does not call a separate raw checker, scan, helper, or Mermaid route
because the renderer invokes that checker in generated mode. The generated
bundle preserves GraphIR v2 and contains exactly these six basenames:

1. `dependency_graph.tsv`
2. `dependency_graph.ir.json`
3. `dependency_graph.md`
4. `dependency_graph.dot`
5. `dependency_graph.html`
6. `manifest.json`

## Runtime Reader Path

1. Read `agents/skills/code-visualization.md`.
   Complete its canonical typed gate before renderer selection.
1. Record a context-derived `Visualization Selection` before rendering:
   - `context_question`
   - `embedding_context`
   - `literal_user_scope`
   - `visualization_source_universe`
   - `projection_coverage_manifest`
   - `canonical_owner_tool_call`
   - `precision_need`
   - `visualization_kind`
   - `question`
   - `source_evidence`
   - `owner_skill_or_tool`
   - `adapter_tool_calls`
   - `renderer`
   - `output_path`
1. Infer the context question, then project it to a diagram family:
   - "what happens in what order": flowchart / activity diagram.
   - "which exact branches and joins exist": control-flow graph.
   - "what calls or imports what": call graph or dependency graph.
   - "who exchanges messages over time": sequence diagram.
   - "how concurrent events overlap": timing diagram or concurrency sequence diagram.
   - "what states can exist and how transitions occur": state-transition diagram.
   - "where data or artifacts move": data-flow diagram.
   - "which types, classes, protocols, or owners relate": class/type diagram or
     architecture map.
   - "where algorithm/proof status sits on implemented operations":
     `$algorithm-flowchart`.
   - "which large graph needs filtering or navigation": `$html-output` after the
     graph source is available.
   Diagram-family selection changes representation only and cannot change the
   immutable universe or manifest membership.
1. For a diagram embedded in a document, infer the local claim, section role,
   reader action, and `visual_plan` slot before choosing the diagram family.
   Pair this skill with `$structure-planning` for the visual plan and
   `$md-style-check` for Mermaid / Markdown checks.
   Treat this as `Document Embedded Diagrams`: the section claim, reader path,
   and embedding context are part of the visualization selection.
1. Route source ownership and delegation through owning skills and packets only.
1. Keep pass/fail authority with the source producer. The diagram is a
   projection of extracted facts; code, dependency, proof, or runtime checkers
   own correctness claims.
1. If the request is repository/code-space dependency visualization, execute
   exactly one matching command from Small-Model Direct Route after the owner
   ToolCall, and retain its adapter ToolCall in the handoff.
1. Run the owning formatter after rendering. Formatter and renderer remain
   syntax/layout-only and cannot extract facts or mutate typed coverage.
1. Handoff and closeout are incomplete unless they carry the complete
   `VisualizationSourceUniverse`, canonical owner ToolCall, every adapter
   ToolCall, `ProjectionCoverageManifest`, final artifact,
   exact eight-kind `source_counts`, `rendered_counts`, and `readback_counts`
   maps for `identity`, `edge`, `field`, `phase`, `branch`, `module`,
   `evidence`, and `time`, deterministic `coverage_digest`,
   `final_token_readback`, and final typed status. If
   capacity prevents complete output, return the typed renderer-capacity
   blocker with no partial artifact.
