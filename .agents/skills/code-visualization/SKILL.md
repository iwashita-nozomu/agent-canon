---
name: code-visualization
description: Use when a request asks to visualize code, repository structure, runtime behavior, state, data movement, dependencies, types, proof state, an interactive graph, or a diagram embedded in a document; infer the user's context question, embedding context, and precision need, select the diagram family and evidence source, then delegate rendering to the owning skill or tool.
---

<!--
@dependency-start
contract skill
responsibility Exposes code visualization selection to Codex skill discovery.
upstream design ../../../agents/skills/code-visualization.md canonical skill document
upstream design ../../../agents/skills/dependency-analysis.md dependency and call graph evidence
upstream design ../../../agents/skills/algorithm-flowchart.md JIT/proof flowchart evidence
upstream design ../../../agents/skills/structure-refactor.md architecture and responsibility-map evidence
upstream design ../../../agents/skills/prose-reasoning-graph.md shared graph projection contract
@dependency-end
-->

# Code Visualization

## Reader Map

- Purpose: runtime skill for selecting the right diagram or visualization route
  for code, repository structure, runtime behavior, proof state, or data flow.
- Use When: a task asks to visualize code, dependencies, state transitions,
  architecture, proofs, or document-embedded diagrams.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/code-visualization.md` selection rules.
- Boundary: visualization must be based on the owning evidence source; diagrams
  do not replace implementation, proof, or dependency checks.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill code-visualization --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

## Small-Model Direct Route

For repository/code-space dependency visualization, use this self-sufficient
route before reading the canonical document or the generic visualization
decision tree. The generated full-scope command is exact:

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

`--json` is invalid; use `--format json`.
`check_dependency_graph.sh` owns dependency pass/fail authority. In generated
mode, the renderer invokes that checker for the
generated TSV and owns only Graph IR, Markdown, DOT, HTML, and bundle/manifest
projection creation. For a supplied TSV, checker status is `not_run`: the
supplied TSV producer owns source facts and the renderer owns only projections.
This route does not call a separate raw checker, scan, helper, or Mermaid route
because the renderer invokes that checker in generated mode. The generated
bundle contains exactly these six basenames:

1. `dependency_graph.tsv`
2. `dependency_graph.ir.json`
3. `dependency_graph.md`
4. `dependency_graph.dot`
5. `dependency_graph.html`
6. `manifest.json`

1. Read `agents/skills/code-visualization.md`.
1. If the request is repository/code-space dependency visualization, follow the
   Source Evidence Routes in `agents/skills/code-visualization.md` only.
1. Record a context-derived `Visualization Selection` before rendering:
   - `context_question`
   - `embedding_context`
   - `precision_need`
   - `visualization_kind`
   - `question`
   - `source_evidence`
   - `owner_skill_or_tool`
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
