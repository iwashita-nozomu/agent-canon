<!--
@dependency-start
contract reference
responsibility Defines how dependency header graph evidence enters structured prose and report analysis.
upstream design README.md structured analysis package index
upstream design database-design.md defines SQLite tables and validation boundary
upstream design code-analysis.md defines code dependency adapter scope
upstream design ../dependency-manifest-design.md defines dependency manifest DSL and graph semantics
upstream design ../tools/render_dependency_manifest_graph.md documents dependency graph report rendering
upstream implementation ../../rust/agent-canon/src/graph.rs owns canonical graph storage and query projections
upstream implementation ../../tools/agent_tools/graph_client.py exposes typed Python graph responses
upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency evidence separately
@dependency-end
-->

# Dependency Header Analysis Adapter

この文書は、`@dependency-start` manifest graph を structured analysis に取り込む
adapter contract を定義する。目的は、report 内の claim、設計文書、実装 surface、
dependency header の整合を同じ検証面で扱えるようにすることである。

## Reader Map

- Owns how dependency-header graph evidence enters structured prose and report
  analysis.
- Main path: Inputs, Adapter Boundary, Import Mapping, Report Trace,
  Diagnostics, Presentation Recommendations, and Extraction Notes.
- Read this before joining dependency headers, canonical graph facts, code
  evidence, and report claims in structured analysis.
- Boundary: dependency headers are artifact context contracts, not prose
  sentence nodes or code dependency edges.

## Inputs

| Input | Source | Meaning |
| --- | --- | --- |
| Dependency manifest block | file header | human/agent が読むべき upstream/downstream context。 |
| Canonical graph query | `agent-canon graph query --all --relation dependency --direction both --depth 0` | typed manifest facts with provenance。 |
| Manifest context | `agent-canon graph context --path <repo-path>` | parser-owned present/contract/responsibility items。 |
| Dependency graph report | `render_dependency_manifest_graph.py` | review-readable graph summary。 |
| Code dependency output | `scan_code_dependencies.sh` | import/include/source evidence。manifest graph とは別。 |

## Adapter Boundary

Dependency header graph は、文章 graph の sentence node ではない。これは repository
artifact 間の context contract である。Structured analysis は、report claim がどの
artifact、header edge、code edge、check run に依存しているかを参照するだけでよい。

このため、次を禁止する。

- dependency manifest edge と code import/include edge を同じ relation table に混ぜる。
- dependency header の存在だけで report claim を supported 扱いにする。
- graph report を citation、logic review、merge authority の代替にする。
- generated report artifact を `documents/` の正本として扱う。

The adapter consumes only canonical graph JSON. The Rust `ManifestParser`
validates full files and the contract registry during source snapshot capture;
Graph DSL validation owns SQLite shape and relation constraints. Python uses
`GraphClient` and `GraphResponse.dependency_facts`, while shell tools use fixed
graph status/query/context argument arrays. No adapter tokenizes headers,
normalizes dependency targets, decodes a parallel transport, or opens the
SQLite database directly.

## Import Mapping

| Manifest artifact | DB table | Required fields |
| --- | --- | --- |
| Graph endpoint node | `nodes` | stable ID, path or selector, source payload, producer evidence |
| `GraphDependencyFact` | `edges` / projection payload | stable fact ID, direction, kind, endpoints, reason, producer, span, evidence, authority |
| code import/include/source row | `deps.code_edges` | `language`, `kind`, `source_artifact_id`, `target_locator`, `symbol` |
| `GraphDiagnostic` | `diagnostics` and report findings | set, code, severity, path/target, producer, evidence reference |
| Manifest context item | source-node payload / context projection | present, contract, responsibility, parser span and authority |

Artifact id は path hash だけではなく、repo id、path、content hash、tool provenance から作る。
rename の検出は future work だが、adapter は `payload_json` に previous locator を残せる。

## Report Trace

Report 側では、claim が dependency evidence を使うときに次の形で辿れるようにする。

```text
report.claims.claim_id
  -> report.evidence_refs.target_id = artifact:...
  -> deps.artifacts.artifact_id
  -> deps.dependency_edges / deps.code_edges
  -> report.check_runs
```

この trace により、設計レポート内の一文が、どの source document、どの dependency
header、どの checker evidence に基づくかを確認できる。

## Diagnostics

Adapter は次の finding を structured analysis 側へ渡す。

| Rule | Severity | Meaning |
| --- | --- | --- |
| `missing_dependency_header` | blocker | claim が参照する artifact に manifest がない。 |
| `broken_dependency_target` | blocker | manifest target path が存在しない。 |
| `self_dependency_edge` | blocker | artifact が自分自身へ dependency edge を持つ。 |
| `dependency_cycle` | warn or blocker | upstream/downstream graph に cycle がある。profile で扱いを決める。 |
| `missing_reverse_edge` | warn | strict bidirectional migration で reverse edge がない。 |
| `stale_report_evidence` | warn | report claim が古い check run または古い content hash を参照している。 |
| `unsupported_report_claim` | blocker | strong claim が artifact / source anchor / check run に接続していない。 |

`dependency_cycle` は既存 baseline debt として report-only にできるが、その場合も finding
として materialize し、report が cycle absence を主張しないようにする。

## Presentation Recommendations

Dependency header graph は文章ではなく構造を見せた方が読みやすい場合が多い。
Projection view は次を推奨できる。

| Graph shape | Recommended format |
| --- | --- |
| high-degree dependency node | figure |
| manifest edge inventory | table |
| repair or validation steps | ordered list |
| few local edges with short reason | prose |

Format recommendation は report rendering hint であり、dependency graph の入力仕様には使いません。

## Extraction Notes

独立 tool 化時は、dependency manifest parser、code dependency scanner、prose graph
adapter を同じ package に入れてよい。ただし package 内でも次の境界を保つ。

- Manifest DSL は `dependency-manifest-design.md` の文法を正とする。
- Prose DSL は Prose Reasoning Graph DSL を正とする。
- DB schema は `database-design.md` を正とする。
- AgentCanon skill、PR workflow、submodule update policy は package core に入れない。
