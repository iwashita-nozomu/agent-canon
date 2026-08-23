<!--
@dependency-start
contract skill
responsibility Owns the canonical typed code visualization contract and renderer delegation for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design dependency-analysis.md dependency graph and function-call evidence
upstream design algorithm-flowchart.md JIT-canonical algorithm and proof-state charts
upstream design structure-refactor.md architecture and responsibility-map evidence
upstream design prose-reasoning-graph.md shared graph projection contract
upstream design html-output.md browser-readable rendering route
upstream implementation ../../tools/agent_tools/visualization_contract.py owns the exact D2.4 seven-function API and ToolCall validation
upstream implementation ../../tools/agent_tools/route.py emits the singular canonical owner route
downstream implementation ../../.agents/skills/code-visualization/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# code-visualization

## Reader Map

- Purpose: act as the sole public visualization owner, build the complete typed
  source universe and coverage manifest, then choose a renderer without changing
  universe membership.
- Section path: Canonical Contract And Ownership fixes the pre-render contract;
  Context Diagnosis and Question-To-Diagram Projection choose only the view;
  Source Evidence Routes and Renderer Choice delegate fact extraction and
  syntax/layout; Handoff Packet and Closeout require post-format readback.
- Use when: a task asks to visualize code, dependencies, runtime behavior,
  state, data movement, types, proof status, or repository structure.
- Boundary: `code-visualization` is the sole public visualization owner. Source
  facts stay with producer skills and tools; renderer skills and tools own only
  syntax/layout projection and cannot change source-universe membership.

## Purpose

`code-visualization` は、コードや repository を図示するときに、ユーザーや文書の
読者が何を理解したいのかを文脈から分類し、その問いに合う図の種類、source
evidence、所有 skill / tool、renderer を選ぶ skill です。

この skill は唯一の public visualization owner です。図種を選ぶ前に、typed
source universe、coverage manifest、canonical owner ToolCall を確定します。
依頼文の対象、時間軸、必要な厳密さ、読者、source fact の所在から判断します。
source fact の抽出は
`dependency-analysis`、`structure-refactor`、`algorithm-flowchart`、
`prose-reasoning-graph` などの owner に委譲し、図は抽出済み fact の projection
として扱います。

## Canonical Contract And Ownership

`code-visualization` is the sole public entrypoint and policy owner for every
visualization. `tools/agent_tools/visualization_contract.py` is the single exact
typed implementation module for `VisualizationSourceUniverse`,
`ProjectionCoverageManifest`, canonical `ToolCall` validation, deterministic
coverage/readback digests, and typed rejection statuses. Skills and renderers
must reference those types; they must not define local substitutes or a second
omission/granularity policy.

Its fixed public functions are `build_source_universe`,
`build_projection_coverage_manifest`, `validate_projection_coverage`,
`serialize_tool_call`, `serialize_projection_identity`,
`serialize_projection_coverage_manifest`, and `readback_projection`. No adapter
calls an underscore-prefixed owner helper. Final-artifact
readback is external to renderers and is supplied to
`validate_projection_coverage(..., readback=...)`.

Before selecting a diagram family or renderer, perform this ordered gate:

1. Declare `code-visualization` as the sole public owner; reject a missing owner
   instead of selecting a renderer directly.
2. Preserve the literal user scope exactly and compute its complete source-fact
   owner closure and dependency closure.
3. Construct one `VisualizationSourceUniverse` containing every identity and
   relation in that union. Membership is immutable for the rest of the run.
4. Construct a `ProjectionCoverageManifest` with an entry for every universe
   identity and relation. Rendering may add projection/readback evidence to an
   entry but may not delete, aggregate, substitute, or narrow one.
5. Validate the schema-bearing canonical owner `ToolCall` before selecting or
   invoking any renderer adapter.
6. Obtain every artifact locator from `serialize_projection_identity` and the
   marker only from `serialize_projection_coverage_manifest`, passing the
   owner ToolCall first and the artifact adapter ToolCall second.

| ToolCall role | `tool_id` | `argument_schema` | Contract |
| --- | --- | --- | --- |
| Canonical visualization owner | `agent_canon.visualization.coverage` | `agent_canon.visualization.arguments.coverage.v1` | Sole public owner; carries the complete literal scope and closure arguments and owns final coverage/readback status. |
| Dependency manifest adapter | `agent_canon.visualization.adapter.dependency_manifest` | `agent_canon.visualization.arguments.dependency_manifest.v1` | Projects dependency-manifest facts without changing producer authority. |
| Algorithm flowchart adapter | `agent_canon.visualization.adapter.algorithm_flowchart` | `agent_canon.visualization.arguments.algorithm_flowchart.v1` | Projects JIT IR, Lean evidence, and theorem-graph facts into syntax/layout. |
| Document Mermaid adapter | `agent_canon.visualization.adapter.document_mermaid` | `agent_canon.visualization.arguments.document_mermaid.v1` | Projects complete document diagram facts into one Mermaid representation. |
| Repository graph adapter | `agent_canon.visualization.adapter.repository_graph` | `agent_canon.visualization.arguments.repository_graph.v1` | Projects complete repository graph facts into static or interactive layout. |
| Knowledge graph adapter | `agent_canon.visualization.adapter.knowledge_graph` | `agent_canon.visualization.arguments.knowledge_graph.v1` | Projects complete prose/knowledge graph facts into layout. |

Every other renderer is likewise a typed adapter ToolCall downstream of the
canonical owner ToolCall. A renderer-local identifier never replaces the
canonical owner call. Executable paths remain literal commands and are never
ToolIDs. Each renderer-only skill references this section rather than defining
another omission or granularity policy.

Literal user scope plus owner/dependency closure is immutable. It must never be
pruned, aggregated away, top-N ranked, represented by samples, reduced to a
main path, stripped of helpers, narrowed for importance/readability, or replaced
by a summary fallback. Diagram-family choice changes only representation.
Clustering, zoom, expansion, and filtering are reversible view state: every
source identity remains serialized in the final artifact and discoverable from
any view state.

After rendering, the owning formatter is mandatory. Formatting owns only
syntax/layout and cannot extract source facts or change the universe or
manifest. Run canonical post-format readback over the final artifact and
produce exact eight-kind `source_counts`, `rendered_counts`, and
`readback_counts` maps for `identity`, `edge`, `field`, `phase`, `branch`,
`module`, `evidence`, and `time`, plus the deterministic `coverage_digest` and
`final_token_readback`. Coverage is
complete only when the typed contract accepts the final manifest and readback.
If a renderer cannot represent the complete universe, return the typed
renderer-capacity rejection from `visualization_contract.py`; never prune or
fall back to a partial artifact.

## Context Diagnosis

図を作る前に、依頼文を次の context に分解します。

| Field | Meaning |
| --- | --- |
| `context_question` | 読者が図で答えたい問い。例: order、branch precision、call relation、interaction over time、state lifecycle、data movement、module dependency、concurrency timing、type responsibility |
| `scope` | literal user scope plus its complete source-owner and dependency closure |
| `time_axis` | 時間順序が中心か、静的な関係が中心か |
| `precision_need` | identity-complete orientation、exact branch graph、review trace、interactive inspection など。precision は universe membership を変更しない |
| `source_fact_owner` | code analyzer、dependency manifest、trace/log、schema、workflow contract、JIT-canonical IR など |
| `reader_action` | 読者が図を見て行う判断。例: review、debug、refactor、test design、proof navigation、interactive inspection |
| `embedding_context` | 図を文書に埋め込む場合の section、claim、reader path、`visual_plan` slot |

この context を埋めてから図種へ射影します。図種がユーザー文面に直接書かれている
場合も、context と矛盾しないか確認します。例: 「処理順を見たいコールグラフ」は
order と call relation の両方を要求するため、必要な projection をすべて作ります。
どの図種も typed universe を縮小しません。

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
  literal_user_scope: <exact requested function, class, service, package, workflow, repository, or proof artifact>
  visualization_source_universe: <complete typed universe including owner/dependency closure>
  projection_coverage_manifest: <typed manifest with one entry per universe identity and relation>
  canonical_owner_tool_call: <agent_canon.visualization.coverage schema-bearing ToolCall>
  time_axis: <static relation | ordered execution | concurrent time | state lifecycle>
  precision_need: <identity-complete orientation | exact branch graph | review trace | interactive exploration>
  visualization_kind: <kind>
  question: <what the diagram must answer>
  source_evidence: <command output, manifest, trace, IR, or graph artifact>
  owner_skill_or_tool: <skill or tool that owns the source facts>
  adapter_tool_calls: <typed renderer/formatter adapter ToolCalls downstream of the owner call>
  renderer: <Mermaid, DOT/Graphviz, HTML dashboard, notebook, or existing viewer>
  output_path: <path for the rendered or embedded artifact>
```

## Question-To-Diagram Projection

| Context question | Visualization kind | Use for | Source owner |
| --- | --- | --- | --- |
| What happens in what order? | フローチャート / アクティビティ図 | `if`、loop、全分岐と処理手順の説明 | local code read; `$algorithm-flowchart` for JIT/proof overlays |
| Which exact branches and joins exist? | 制御フローグラフ | compiler、static analysis、test design 向けの branch / join / loop | language analyzer or compiler artifact; `$test-design` for test use |
| What calls or imports what? | コールグラフ / 依存関係図 | function call relation、file / package / skill dependency | `$dependency-analysis` |
| Who exchanges messages over time? | シーケンス図 | API、class、service 間の時系列通信 | call traces, code entrypoint read, interface docs |
| How do concurrent events overlap? | タイミング図 / 並行シーケンス図 | thread、event、async task、queue、race point | trace/log artifacts, async entrypoints, runtime contracts |
| What states can exist and how do transitions occur? | 状態遷移図 | login、job lifecycle、workflow stage、retry state など | state enum, transition table, workflow contract |
| Where does data or an artifact move? | データフロー図 | input、transform、store、output、artifact movement | data schema, IO code, dependency packet |
| Which types, classes, protocols, or owners relate? | クラス図 / 型図 / architecture map | class、protocol、interface、ownership boundary | language-specific review; `$oop-readability-check`; `$structure-refactor` |
| Where does proof or algorithm status sit on implemented operations? | algorithm/proof overlay | JIT-canonical operation path and theorem graph status | `$algorithm-flowchart` |
| Which large graph needs filtering, navigation, or sharing? | HTML graph / dashboard | complete graph inspection with reversible view state | `$html-output` after source graph exists |

When several questions are present, choose every projection required to answer
them. `reader_action` and diagram-family selection choose representation and
layout only; they do not establish a primary-only completion path or make any
covered projection optional. Each projection remains accountable to the same
immutable universe and typed manifest.

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
- which identity-complete projection slot carries the claim without replacing
  or suppressing any universe identity or relation.

## Source Evidence Routes

Complete the Canonical Contract And Ownership gate before applying a selected
owner skill or renderer. For repository/code-space dependency visualization,
the small-model direct route is self-sufficient after that gate:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json
```

Use this exact changed-scope command only when changed scope is explicit:

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json
```

Treat these two commands as immutable flag templates. Copy the selected
command with every shown flag: `--root .` and `--format json` are mandatory in
both routes. Do not remove, add, or rename any flag.

`--json` is invalid; use `--format json`.
The canonical graph owns dependency status and facts. The renderer performs one
typed dependency query through `GraphClient` and owns only Graph IR, Markdown,
DOT, HTML, and bundle/manifest projection creation. There is no supplied-input,
raw-checker, scan, helper, or Mermaid fallback. Its
generated bundle contains exactly these six basenames:

1. `dependency_graph.tsv`
2. `dependency_graph.ir.json`
3. `dependency_graph.md`
4. `dependency_graph.dot`
5. `dependency_graph.html`
6. `manifest.json`

The renderer invocation is an adapter ToolCall downstream of the canonical
`agent_canon.visualization.coverage` owner ToolCall:

- owner `tool_id = agent_canon.visualization.coverage`
- owner `argument_schema = agent_canon.visualization.arguments.coverage.v1`
- adapter `tool_id = agent_canon.visualization.adapter.dependency_manifest`
- adapter `argument_schema = agent_canon.visualization.arguments.dependency_manifest.v1`

The owner call is recorded first and the dependency adapter call second. The
literal Python command above remains the execution surface; its executable
path is not a ToolID.

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

Renderer choice occurs only after universe, manifest, and canonical owner
ToolCall validation. It changes syntax/layout only and cannot change coverage.

- Mermaid is the default for Markdown flowchart, sequence, state, class/type,
  and data-flow projections when it can retain the complete universe.
- DOT / Graphviz is the default for dense dependency or call graphs when edge
  count or layout stability matters.
- HTML dashboard is selected when the user requests browser interaction,
  filtering, navigation, or inspection of a large graph.
- Notebook visualization is selected for experiment results and reads existing
  run artifacts from the experiment result directory.
- JIT-canonical algorithm diagrams use `algorithm-flowchart` and its current
  IR / Lean / theorem graph evidence route.

Algorithm artifacts use
`renderer_id = agent_canon.visualization.adapter.algorithm_flowchart`, serialize
the owner ToolCall before that adapter ToolCall, map every identity through
`serialize_projection_identity`, and obtain the marker only through
`serialize_projection_coverage_manifest`. They render exactly one Mermaid
diagram with no Markdown table fallback, run the Rust Markdown/Mermaid
formatter, then call `readback_projection` and
`validate_projection_coverage(..., readback=...)`. The resulting typed
`diagram_count_mismatch` or `table_fallback` violation is authoritative; Rust
owns syntax formatting only.

Graph renderers preserve GraphIR v2. Interactive clustering, zoom, expansion,
and filtering alter only reversible view state; all identities remain present
and discoverable in the serialized final artifact. After rendering, invoke the
mandatory owning formatter, then run canonical final-artifact readback. A
renderer or formatter capacity problem returns the typed capacity blocker
instead of a reduced, summarized, or alternate partial result.

## Handoff Packet

Every renderer handoff and return uses this complete packet:

```text
Visualization Handoff:
  visualization_source_universe:
  projection_coverage_manifest:
  canonical_owner_tool_call:
  adapter_tool_calls:
  visualization_kind:
  embedding_context:
  source_artifacts:
  source_fact_owner:
  renderer:
  mandatory_formatter:
  audience:
  final_artifact:
  source_counts: <all eight source kinds>
  rendered_counts: <all eight source kinds>
  readback_counts: <all eight source kinds reconstructed from final bytes>
  coverage_digest:
  final_token_readback:
  typed_capacity_blocker:
```

The universe and manifest fields are complete typed values, not selections or
display hints. `typed_capacity_blocker` is null on success; on capacity failure
it carries the typed rejection produced by `visualization_contract.py`, and no
partial artifact is accepted.

## Closeout

Closeout cites:

- the `Visualization Selection` record;
- the `embedding_context` when the diagram is embedded in a document;
- the complete `VisualizationSourceUniverse` and
  `ProjectionCoverageManifest`;
- the schema-bearing canonical owner ToolCall and every downstream adapter
  ToolCall;
- the source evidence command/artifact and producer that retains fact
  authority;
- the selected renderer, mandatory formatter, and final artifact;
- all-eight-kind `source_counts`, `rendered_counts`, and `readback_counts` maps;
- the deterministic `coverage_digest` and `final_token_readback`;
- final typed coverage status, or the typed renderer-capacity blocker when no
  complete artifact can be produced.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

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
