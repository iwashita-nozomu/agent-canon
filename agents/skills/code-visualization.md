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
upstream implementation ../../tools/validation/semantic/tools/visualization_contract.py owns the exact D2.4 seven-function API and ToolCall validation
upstream implementation ../../tools/agent/orchestration/route.py emits the singular canonical owner route
downstream implementation ../../.codex/personal/skills/code-visualization/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# code-visualization

## Reader Map

- Purpose: own visualization selection, source-fact routing, and renderer
  boundaries; use typed coverage when the selected route needs a completeness
  guarantee.
- Section path: Canonical Contract And Ownership defines the typed coverage
  route; Context Diagnosis and Question-To-Diagram Projection select a useful
  view; source evidence, renderer, handoff, and closeout depend on the chosen
  source and completeness contract.
- Use when: a task asks to visualize code, dependencies, runtime behavior,
  state, data movement, types, proof status, or repository structure.
- Boundary: `code-visualization` is the sole public visualization owner. Source
  facts stay with producer skills and tools; renderer skills and tools own only
  syntax/layout projection and cannot change source-universe membership.

## Purpose

`code-visualization` は、コードや repository を図示するときに、ユーザーや文書の
読者が何を理解したいのかを文脈から分類し、その問いに合う図の種類、source
evidence、所有 skill / tool、renderer を選ぶ skill です。

この skill は唯一の public visualization owner です。依頼文の対象、時間軸、必要な
厳密さ、読者、source fact の所在から、必要な source evidence と coverage contract を
選びます。complete graph coverage を求める場合や、選択 route が typed coverage を
要求する場合は typed source universe、coverage manifest、canonical owner ToolCall を使います。
source fact の抽出は
`dependency-analysis`、`structure-refactor`、`algorithm-flowchart`、
`prose-reasoning-graph` などの owner に委譲し、図は抽出済み fact の projection
として扱います。

## Canonical Contract And Ownership

`code-visualization` is the sole public entrypoint and policy owner for every
visualization. `tools/validation/semantic/tools/visualization_contract.py` is the single exact
typed implementation module for `VisualizationSourceUniverse`,
`ProjectionCoverageManifest`, canonical `ToolCall` validation, deterministic
coverage/readback digests, and typed rejection statuses. On the typed route,
skills and renderers reference those types and do not define local substitutes
or a second omission/granularity policy.

Its fixed public functions are `build_source_universe`,
`build_projection_coverage_manifest`, `validate_projection_coverage`,
`serialize_tool_call`, `serialize_projection_identity`,
`serialize_projection_coverage_manifest`, and `readback_projection`. No adapter
calls an underscore-prefixed owner helper. Final-artifact
readback is external to renderers and is supplied to
`validate_projection_coverage(..., readback=...)`.

When the selected visualization promises complete identity/relation coverage or
uses a renderer that requires typed coverage, perform this gate:

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

On the typed route, every renderer is a typed adapter ToolCall downstream of
the canonical owner ToolCall. A renderer-local identifier never replaces that
owner call. Executable paths remain literal commands and are never ToolIDs.
Renderer-only skills reference this section when they use typed coverage.

These types and functions apply when the selected route uses typed coverage. A
bounded explanatory diagram does not need a fabricated universe, manifest, or
ToolCall. Do not create local substitutes for typed operations.

On the typed complete-coverage route, literal user scope plus owner/dependency
closure is immutable. Do not prune, aggregate, sample, or replace it with a
summary. For a bounded explanatory diagram, keep the requested scope explicit
and do not imply that omitted code or relations are covered. Clustering, zoom,
expansion, and filtering are reversible view state when the artifact promises
complete coverage.

Use the selected formatter and readback route needed by the artifact. On the
typed complete-coverage route, formatting cannot change the universe or
manifest; run canonical post-format readback and retain the exact eight-kind
counts, digest, and final token readback. Coverage is complete only when the
typed contract accepts the final manifest and readback. If a renderer cannot
represent that complete universe, return its typed capacity rejection rather
than a partial artifact.

## Context Diagnosis

図を作る前に、依頼文を次の context に分解します。

| Field | Meaning |
| --- | --- |
| `context_question` | 読者が図で答えたい問い。例: order、branch precision、call relation、interaction over time、state lifecycle、data movement、module dependency、concurrency timing、type responsibility |
| `scope` | exact bounded view scope; the typed route adds its complete source-owner and dependency closure |
| `time_axis` | 時間順序が中心か、静的な関係が中心か when it affects the diagram |
| `precision_need` | identity-complete orientation、exact branch graph、review trace、interactive inspection など。typed coverage membership is fixed by its contract |
| `source_fact_owner` | code analyzer、dependency manifest、trace/log、schema、workflow contract、JIT-canonical IR など |
| `reader_action` | 読者が図を見て行う判断。例: review、debug、refactor、test design、proof navigation、interactive inspection |
| `embedding_context` | 図を文書に埋め込む場合の section、claim、reader path、`visual_plan` slot |

Select the context dimensions that affect the requested diagram. Always resolve
the reader's question and scope; include time axis, precision, source owner,
reader action, or embedding context when they change the source evidence or
representation. If the request names a diagram family, check that it answers
the question. Add another projection only when one view would leave a requested
relation unexplained. A typed complete-coverage diagram keeps its universe
unchanged.

文書に図を埋め込む場合は、この skill で local claim と reader question を確認します。
section structure や reader path も変わるときは `structure-planning` を使います。
README、design doc、report、skill 文書、workflow 文書、または
`structure-planning` の `visual_plan` で図が必要になったら、必要な source evidence を
選んでから図種を決めます。
「Mermaid 図を入れる」だけでは図種を確定せず、その section の claim、読者の
次の行動、source evidence から flowchart、sequence diagram、state-transition
diagram、dependency graph などへ射影します。

## Visualization Selection Record

Use a selection record when multiple source/renderer choices remain or a
renderer handoff needs one. Record only the fields that affect that decision;
the typed route and a renderer's existing contract retain their required values.

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

When several questions are present, choose the smallest set of projections that
answers them. `reader_action` and diagram-family selection choose representation
and layout; they do not change source-fact authority. A typed complete-coverage
route keeps each selected projection accountable to its same universe and
manifest.

## Document Embedded Diagrams

Use this skill when a diagram will be embedded in Markdown, report prose,
design docs, README, workflow docs, skill docs, or a `visual_plan`. Use
`$structure-planning` when the document structure or reader path changes, and
select `$md-style-check` for Markdown syntax, Mermaid, link, or heading checks
that the edited document needs.

For embedded diagrams, decide:

- which section claim the diagram supports;
- what the reader should be able to decide after seeing it;
- whether the source fact is code, dependency manifest, trace/log, schema,
  workflow contract, proof graph, or prose graph;
- whether the diagram claims complete identity coverage or explains a bounded
  source region, and what evidence supports that claim.

## Source Evidence Routes

For complete typed coverage, complete the Canonical Contract And Ownership gate
before applying the selected renderer. For repository/code-space dependency
visualization, use the existing direct route when a dependency graph is requested:

```bash
python3 tools/analysis/dependencies/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json
```

Use this exact changed-scope command only when changed scope is explicit:

```bash
python3 tools/analysis/dependencies/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json
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

[documents/tools/render_dependency_manifest_graph.md](../../documents/tools/render_dependency_manifest_graph.md)

For non-code-space visualization, delegate source ownership through the
related skill that owns the facts: `$dependency-analysis` for dependency and
call relations, `$structure-refactor` for architecture and responsibility
maps, `$algorithm-flowchart` for algorithm/proof overlays,
`$prose-reasoning-graph` for prose graphs, `$html-output` for browser-readable
large-graph views, and `$md-style-check` for embedded Markdown diagrams.
Follow each related skill's current owner and native entrypoint; this selector
describes the ownership route without reproducing or regenerating private command
definitions.

## Renderer Choice

For typed complete-coverage output, choose the renderer after universe, manifest,
and canonical owner ToolCall validation. In all routes, the renderer changes
syntax/layout only and cannot change source-fact authority.

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

When GraphIR v2 or another complete-coverage contract is selected, preserve its
identities through reversible view state and use its required formatter and
final-artifact readback. If the typed renderer cannot represent the complete
universe, return the typed capacity blocker instead of a partial artifact.

## Handoff Packet

Use this complete packet when a renderer handoff uses typed coverage or its
existing contract requires these fields. A local bounded diagram with no
renderer handoff does not need a fabricated packet:

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

Closeout records evidence for the selected route. For typed complete coverage,
include:

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

For a bounded local diagram, cite the source owner and scope, plus the final
artifact or embedding location.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

Use the selected source route and renderer contract:

- Resolve the reader's question and requested scope; choose the diagram family
  that answers it and add another projection only when a requested relation
  would otherwise be unclear.
- Route source facts through their owning skill or tool. The diagram does not
  take correctness authority from code, dependency, proof, or runtime producers.
- Use typed universe, manifest, ToolCalls, formatter, and readback when the
  selected output claims complete coverage or its existing adapter requires
  them. Preserve that route's exact API and capacity behavior.
- For repository/code-space dependency visualization, use the matching command
  from `Source Evidence Routes`; keep its adapter ToolCall when the typed route
  is selected.
- For an embedded diagram, use `structure-planning` when document structure or
  reader path changes, and select `md-style-check` for the changed Markdown
  properties.
- Use `Handoff Packet` and `Closeout` at their stated scope. Do not create a
  handoff packet or empty coverage fields for a bounded local diagram.
