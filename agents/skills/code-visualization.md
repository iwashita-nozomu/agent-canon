<!--
@dependency-start
contract skill
responsibility Documents code visualization selection for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design dependency-analysis.md dependency graph and function-call evidence
upstream design algorithm-flowchart.md JIT-canonical algorithm and proof-state charts
upstream design structure-refactor.md architecture and responsibility-map evidence
upstream design prose-reasoning-graph.md shared graph projection contract
upstream design html-output.md browser-readable rendering route
downstream implementation ../../.agents/skills/code-visualization/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# code-visualization

## Reader Map

- Purpose: choose the right visualization family, source evidence owner, and
  renderer for code, repository, workflow, proof, or document-embedded diagrams.
- Section path: Purpose and Context Diagnosis classify the reader question;
  Visualization Selection Record and Question-To-Diagram Projection define the
  choice; Document Embedded Diagrams, Source Evidence Routes, Renderer Choice,
  Handoff Packet, and Closeout cover execution.
- Use when: a task asks to visualize code, dependencies, runtime behavior,
  state, data movement, types, proof status, or repository structure.
- Boundary: this skill selects and routes visualizations; source facts stay with
  owner skills such as `dependency-analysis`, `structure-refactor`,
  `algorithm-flowchart`, and `prose-reasoning-graph`.

## Purpose

`code-visualization` は、コードや repository を図示するときに、ユーザーや文書の
読者が何を理解したいのかを文脈から分類し、その問いに合う図の種類、source
evidence、所有 skill / tool、renderer を選ぶ skill です。

この skill は visualization selector です。図種名の有無だけで選ばず、依頼文の
対象、時間軸、必要な厳密さ、読者、source fact の所在から判断します。source
fact の抽出は
`dependency-analysis`、`structure-refactor`、`algorithm-flowchart`、
`prose-reasoning-graph` などの owner に委譲し、図は抽出済み fact の projection
として扱います。

## Context Diagnosis

図を作る前に、依頼文を次の context に分解します。

| Field | Meaning |
| --- | --- |
| `context_question` | 読者が図で答えたい問い。例: order、branch precision、call relation、interaction over time、state lifecycle、data movement、module dependency、concurrency timing、type responsibility |
| `scope` | function、class、service、package、workflow、proof artifact などの対象範囲 |
| `time_axis` | 時間順序が中心か、静的な関係が中心か |
| `precision_need` | 説明用の概観か、compiler / static analysis / test design 向けの正確な分岐か |
| `source_fact_owner` | code analyzer、dependency manifest、trace/log、schema、workflow contract、JIT-canonical IR など |
| `reader_action` | 読者が図を見て行う判断。例: review、debug、refactor、test design、proof navigation、interactive inspection |
| `embedding_context` | 図を文書に埋め込む場合の section、claim、reader path、`visual_plan` slot |

この context を埋めてから図種へ射影します。図種がユーザー文面に直接書かれている
場合も、context と矛盾しないか確認します。例: 「処理順を見たいコールグラフ」は
call relation ではなく order の問いなので、flowchart / activity diagram を主候補
にし、call graph は補助図にします。

文書に図を埋め込む場合も同じです。README、design doc、report、skill 文書、
workflow 文書、`structure-planning` の `visual_plan` で図が必要になったら、この
skill で `context_question` と `embedding_context` を決めてから図種を選びます。
「Mermaid 図を入れる」だけでは図種を確定せず、その section の claim、読者の
次の行動、source evidence から flowchart、sequence diagram、state-transition
diagram、dependency graph などへ射影します。

## Visualization Selection Record

図を作る前に次の record を残します。

```text
Visualization Selection:
  context_question: <reader question inferred from the request>
  embedding_context: <document section, claim, reader path, visual_plan slot, or not_embedded>
  scope: <function, class, service, package, workflow, repository, or proof artifact>
  time_axis: <static relation | ordered execution | concurrent time | state lifecycle>
  precision_need: <overview | exact branch graph | review trace | interactive exploration>
  visualization_kind: <kind>
  question: <what the diagram must answer>
  source_evidence: <command output, manifest, trace, IR, or graph artifact>
  owner_skill_or_tool: <skill or tool that owns the source facts>
  renderer: <Mermaid, DOT/Graphviz, HTML dashboard, notebook, or existing viewer>
  output_path: <path for the rendered or embedded artifact>
```

## Question-To-Diagram Projection

| Context question | Visualization kind | Use for | Source owner |
| --- | --- | --- | --- |
| What happens in what order? | フローチャート / アクティビティ図 | `if`、loop、処理手順、主要 path の説明 | local code read; `$algorithm-flowchart` for JIT/proof overlays |
| Which exact branches and joins exist? | 制御フローグラフ | compiler、static analysis、test design 向けの branch / join / loop | language analyzer or compiler artifact; `$test-design` for test use |
| What calls or imports what? | コールグラフ / 依存関係図 | function call relation、file / package / skill dependency | `$dependency-analysis` |
| Who exchanges messages over time? | シーケンス図 | API、class、service 間の時系列通信 | call traces, code entrypoint read, interface docs |
| How do concurrent events overlap? | タイミング図 / 並行シーケンス図 | thread、event、async task、queue、race point | trace/log artifacts, async entrypoints, runtime contracts |
| What states can exist and how do transitions occur? | 状態遷移図 | login、job lifecycle、workflow stage、retry state など | state enum, transition table, workflow contract |
| Where does data or an artifact move? | データフロー図 | input、transform、store、output、artifact movement | data schema, IO code, dependency packet |
| Which types, classes, protocols, or owners relate? | クラス図 / 型図 / architecture map | class、protocol、interface、ownership boundary | language-specific review; `$oop-readability-check`; `$structure-refactor` |
| Where does proof or algorithm status sit on implemented operations? | algorithm/proof overlay | JIT-canonical operation path and theorem graph status | `$algorithm-flowchart` |
| Which large graph needs filtering, navigation, or sharing? | HTML graph / dashboard | large graph inspection, report artifact, viewer sharing | `$html-output` after source graph exists |

When several questions are present, choose a primary diagram by `reader_action`
and keep secondary diagrams as optional handoff items. Example: debugging an
async API issue usually selects a sequence diagram or timing diagram over a
static dependency graph, while refactoring package boundaries selects a
dependency graph or architecture map over a sequence diagram.

## Document Embedded Diagrams

Use this skill when a diagram will be embedded in Markdown, report prose,
design docs, README, workflow docs, skill docs, or a `visual_plan`. The diagram
choice is part of the document structure, so pair it with `$structure-planning`
when the document structure or reader path changes, and close Markdown syntax,
Mermaid, links, and heading checks with `$md-style-check`.

For embedded diagrams, decide:

- which section claim the diagram supports;
- what the reader should be able to decide after seeing it;
- whether the source fact is code, dependency manifest, trace/log, schema,
  workflow contract, proof graph, or prose graph;
- whether the diagram is the primary visual, a supporting visual, or a
  replacement for prose that would otherwise repeat an edge list.

## Source Evidence Routes

Use the command packet before applying the selected owner skill. For
repository/code-space dependency visualization, the small-model direct route
is self-sufficient and precedes canonical/generic visualization choices:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json
```

Use this exact changed-scope command only when changed scope is explicit:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json
```

For a supplied TSV hold-out, use the same renderer with the supplied path:

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
This direct route does not call a separate raw checker, scan, helper, or
Mermaid route because the renderer invokes that checker in generated mode. Its
generated bundle contains exactly these six basenames:

1. `dependency_graph.tsv`
2. `dependency_graph.ir.json`
3. `dependency_graph.md`
4. `dependency_graph.dot`
5. `dependency_graph.html`
6. `manifest.json`

Read the detailed renderer contract in:

`documents/tools/render_dependency_manifest_graph.md`

For non-code-space visualization, delegate source ownership through the
related skill that owns the facts: `$dependency-analysis` for dependency and
call relations, `$structure-refactor` for architecture and responsibility
maps, `$algorithm-flowchart` for algorithm/proof overlays,
`$prose-reasoning-graph` for prose graphs, `$html-output` for browser-readable
large-graph views, and `$md-style-check` for embedded Markdown diagrams.
Follow each related skill's current command packet; this selector describes the
ownership route without reproducing those commands.

## Renderer Choice

- Mermaid is the default for compact Markdown diagrams: flowchart, sequence,
  state, class/type, and simple data-flow views.
- DOT / Graphviz is the default for dense dependency or call graphs when edge
  count or layout stability matters.
- HTML dashboard is selected when the user requests browser interaction,
  filtering, navigation, or inspection of a large graph.
- Notebook visualization is selected for experiment results and reads existing
  run artifacts from the experiment result directory.
- JIT-canonical algorithm diagrams use `algorithm-flowchart` and its current
  IR / Lean / theorem graph evidence route.

## Handoff Packet

When another skill renders the diagram, pass this compact packet:

```text
Diagram Handoff:
  visualization_kind:
  embedding_context:
  source_artifacts:
  selected_nodes_or_paths:
  renderer:
  audience:
  required_labels:
  excluded_labels:
  output_path:
```

`required_labels` names the code or artifact identifiers that must appear in
the diagram. `excluded_labels` names generated、stale、or out-of-scope surfaces
that the renderer should leave out.

## Closeout

Closeout cites:

- the `Visualization Selection` record;
- the `embedding_context` when the diagram is embedded in a document;
- the source evidence command or artifact;
- the selected renderer and output path;
- the owner skill / tool that retains correctness authority.
