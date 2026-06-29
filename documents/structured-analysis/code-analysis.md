<!--
@dependency-start
contract reference
responsibility Defines code dependency analysis scope for the structured analysis package.
upstream design README.md structured analysis package index
upstream design database-design.md defines SQLite tables and DB artifact placement
upstream design ../dependency-manifest-design.md separates code dependency evidence from manifest graph evidence
upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency evidence
downstream design dependency-header-analysis.md joins code evidence with report trace without merging edge semantics
@dependency-end
-->

# Code Analysis Adapter

この文書は、Python、shell、C/C++、Rust などの code dependency 解析を
structured analysis に取り込む adapter contract を定義する。

## Reader Map

- Owns code dependency analysis scope for the structured-analysis package.
- Main path: Scope, Boundary, Import Mapping, Report Trace, and Diagnostics.
- Read this before importing import/include/source evidence into structured
  analysis or joining it with dependency-manifest evidence.
- Boundary: code dependency edges and manifest edges may be joined for
  explanation, but their meanings stay distinct.

## Scope

Code analysis は、実装 surface がどの symbol、file、module、include、source script を
参照しているかを扱う。これは dependency header manifest とは別の evidence である。

| Language family | MVP evidence |
| --- | --- |
| Python | import、from import、package/module locator。 |
| Shell | `source`、`.`、local executable/script reference。 |
| C/C++ | local `#include`、header/source relation。 |
| Rust | `mod`、`use`、crate/module locator。 |

MVP は precise compiler-grade dependency graph を目標にしない。既存 scanner で取れる
best-effort edge を report trace と impact packet に渡す。

## Boundary

次を分ける。

| Graph | Meaning | DB table |
| --- | --- | --- |
| Dependency manifest graph | 人間/agent が読むべき design、implementation、environment context。 | `deps.dependency_edges` |
| Code dependency graph | 言語構文から見える import/include/source relation。 | `deps.code_edges` |
| Prose reasoning graph | source text anchor と claim/evidence/discourse relation。 | `prose.nodes`, `prose.edges` |
| Report contract graph | report root から claim、evidence、finding、action への trace。 | `report.*` |

Manifest edge と code edge を同じ relation として扱うと、「読む context」と「実行時または
build 時の参照」が混ざる。Structured analysis は join して説明してよいが、edge の意味は
保持する。

## Import Mapping

| Code evidence | DB target | Notes |
| --- | --- | --- |
| source file | `deps.artifacts` | `kind = code`、language を `payload_json` に入れる。 |
| imported module / include path | `deps.code_edges.target_locator` | repo 内 artifact に解決できる場合は `target_artifact_id` も payload に入れる。 |
| symbol or module name | `deps.code_edges.symbol` | symbol-level precision がない場合は module/file name。 |
| scanner confidence | `deps.code_edges.confidence` | exact local path は high、unresolved module は low。 |

## Report Trace

Code analysis は、設計文書と実装が mirror しているかを見るときに使う。

```text
report.claims.claim_id
  -> report.evidence_refs.target_id = artifact:code-file
  -> deps.artifacts
  -> deps.code_edges
  -> deps.dependency_edges
  -> prose/source anchors that explain the design
```

この trace により、「設計文書で主張した module boundary が、実装 import/include と
dependency header の両方で支えられているか」を検証できる。

## Diagnostics

| Rule | Severity | Meaning |
| --- | --- | --- |
| `design_code_mirror_missing_code_edge` | warn | 設計 claim が code artifact を参照するが、対応 code edge がない。 |
| `code_edge_without_manifest_context` | warn | code edge はあるが、読むべき design/header context が manifest にない。 |
| `unresolved_code_target` | warn | scanner が target artifact を repo 内で解決できない。 |
| `cross_language_boundary_unexplained` | warn | shell、C++、Rust、Python の boundary を跨ぐが design claim がない。 |

Diagnostics は review seed であり、compiler、type checker、build、test の代替ではない。
