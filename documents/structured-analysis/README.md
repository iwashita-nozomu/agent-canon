<!--
@dependency-start
contract reference
responsibility Collects structured prose, report, and dependency analysis contracts for future extraction from AgentCanon.
upstream design ../README.md AgentCanon document index
downstream design database-design.md defines SQLite-backed intermediate graph storage
downstream design graph-dsl.md defines the shared Graph DSL Core storage contract
downstream design dependency-header-analysis.md defines dependency header graph adapter scope
downstream design code-analysis.md defines code dependency graph adapter scope
downstream design document-canon-analysis.md defines document duplicate and non-canonical document adapter scope
downstream design ../prose-reasoning-graph/dsl-spec.md defines prose reasoning graph DSL
downstream design ../dependency-manifest-design.md defines dependency manifest DSL and validation model
downstream design ../tools/prose_reasoning_graph.md documents prose graph CLI usage
downstream design ../tools/render_dependency_manifest_graph.md documents dependency graph report rendering
@dependency-end
-->

# Structured Analysis

この directory は、文章解析、report 構造解析、dependency header 解析を
AgentCanon から将来切り離す場合の集約先である。既存の正本を移動せず、
独立 tool 化で使う契約、adapter、DB 境界をここに蓄積する。

## Reader Map

- Owns the package-level index for structured-analysis canon and runtime entry
  points.
- Main path: Evidence And Assumption Ledger, Canon Set, Boundary, Runtime Entry
  Point, Layer Model, and Extraction Rule.
- Read this before choosing which structured-analysis adapter or database
  contract to inspect.
- Boundary: it indexes the structured-analysis package; individual adapter and
  DB schemas live in sibling documents.

## Evidence And Assumption Ledger

- Evidence sources:
  `graph-dsl.md`, `database-design.md`, `document-canon-analysis.md`,
  `../prose-reasoning-graph/dsl-spec.md`,
  `../dependency-manifest-design.md`, and
  `../../rust/agent-canon/src/structured_analysis.rs`.
- Assumptions:
  `DSL` in this index refers to the Graph DSL Core contract and its adapter
  profiles. Adapter-specific meanings stay in the linked adapter documents.
- Parent-doc alignment:
  `../README.md` indexes AgentCanon documents. This README indexes the
  structured-analysis contract package.

## Canon Set

| Document | Role |
| --- | --- |
| [graph-dsl.md](graph-dsl.md) | graph-shaped evidence の必要十分な storage contract。 |
| [database-design.md](database-design.md) | prose graph、dependency graph、report contract を SQLite で接続する中間 DB 設計。 |
| [dependency-header-analysis.md](dependency-header-analysis.md) | `@dependency-start` manifest graph を structured analysis 側へ取り込む adapter 設計。 |
| [code-analysis.md](code-analysis.md) | Python、shell、C/C++、Rust などの code dependency evidence を取り込む adapter 設計。 |
| [document-canon-analysis.md](document-canon-analysis.md) | duplicate heading、runtime mirror、generated report、stale name を取り込む adapter 設計。 |
| [Prose Reasoning Graph DSL](../prose-reasoning-graph/dsl-spec.md) | Graph DSL Core 上の prose adapter/profile。 |
| [Dependency Manifest Design](../dependency-manifest-design.md) | dependency header manifest の正本文法と graph validation。 |
| [prose_reasoning_graph.py](../tools/prose_reasoning_graph.md) | prose graph CLI の operator flow。 |
| [render_dependency_manifest_graph.py](../tools/render_dependency_manifest_graph.md) | dependency manifest graph report renderer。 |

## Boundary

- この directory は structured analysis package の候補 root である。
- 既存文書の正本 path は、明示的な migration まで移動しない。
- ここに置く新規文書は、独立 tool 化後も残す contract を扱う。
- 汎用 graph storage の正本は `graph-dsl.md` が持ち、個別 surface の意味論は
  adapter 文書が持つ。
- Run artifact、temporary SQLite DB、generated report はここに置かない。
- Agent skill の routing や authority boundary は `agents/skills/` 側の責務として残す。

## Runtime Entry Point

`agent-canon structured-analysis build --root <workspace> --profile devcontainer`
is the cache-build entrypoint used by DevContainer post-create. It writes
`prose_graph.sqlite` and `diagnostics.sqlite` under
`${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}`.
When `--out-dir` is explicit, only durable report artifacts such as
`document_inventory.json`, `structured_analysis_build.json`, and `exports/`
are written there.

The build is source-to-intermediate-representation only. It materializes
git-visible files as the `artifact` layer, derives directory responsibility
projection nodes from README and child artifact responsibility evidence, imports
document inventory findings as the `document-canon` layer, then materializes
warning rows into the separate `diagnostics.sqlite` database. It does not
rewrite `README.md`, source files, or repository documents.

## Layer Model

Structured analysis は次の面を分ける。

| Layer | Source of truth | Notes |
| --- | --- | --- |
| Artifact graph | git-visible file tree | directory/file nodes、`contains` edges、README-to-directory edges、directory responsibility projections。 |
| Diagnostics graph | analysis warning snapshot | current warning run、severity、rule、target path、suggested action。 |
| Prose source anchors | source document spans | sentence、EDU、paragraph、section の source-truth。 |
| Lower reasoning graph | typed relations over anchors | supports、requires、refines、generalizes、concludes など。 |
| Projection views | derived from lower graph | macro-claim、subtopic、reader-state、recommended format。 |
| Dependency header graph | dependency manifest TSV | design、implementation、environment の upstream/downstream edge。 |
| Code dependency graph | language scanners | Python、shell、C/C++、Rust などの imports/includes/source edges。header manifest graph と混ぜない。 |
| Document canon graph | Rust structured-analysis inventory | active duplicate heading、runtime mirror、generated report、stale name cleanup findings, plus closed issue historical records. |
| Report contract graph | report root to sentence trace | claim、evidence、finding、closure event、action。 |

これらの layer は `graph-dsl.md` の `D, N, E, A, P, X, M` object family に
materialize される。layer / kind の組が edge と node の意味を所有するため、
dependency manifest edge、code import、prose support、proof dependency を同じ
storage table に置いても意味論は混ざらない。

## Extraction Rule

独立 tool 化するときは、この directory を package document root とし、
次を先に満たす。

1. Graph DSL Core、DB schema、adapter vocabulary をこの directory に集約する。
2. AgentCanon 固有の skill routing、PR gate、submodule workflow を外部 package
   の core contract から分離する。
3. `agent-canon structured-analysis` Rust CLI、prose graph prototype、
   dependency header tools、code dependency scanners は、同じ DB 設計を読む
   adapter として扱う。
4. 既存 path から移動する場合は、link、dependency header、tool docs、tests を同じ
   change で更新する。
