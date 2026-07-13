<!--
@dependency-start
contract reference
responsibility Defines how dependency header graph evidence enters structured prose and report analysis.
upstream design README.md structured analysis package index
upstream design database-design.md defines SQLite tables and validation boundary
upstream design code-analysis.md defines code dependency adapter scope
upstream design ../dependency-manifest-design.md defines dependency manifest DSL and graph semantics
upstream design ../tools/render_dependency_manifest_graph.md documents dependency graph report rendering
upstream implementation ../../tools/agent_tools/check_dependency_graph.sh emits dependency manifest graph artifacts
upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency evidence separately
upstream implementation ../../tools/agent_tools/dependency_manifest_records.py decodes normalized transport and projects source-universe evidence
upstream implementation ../../tools/agent_tools/bind_r2_scope.py binds review evidence after the source manifest is fixed
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
- Read this before joining dependency headers, dependency graph TSVs, code
  evidence, and report claims in structured analysis.
- Boundary: dependency headers are artifact context contracts, not prose
  sentence nodes or code dependency edges.

## Inputs

| Input | Source | Meaning |
| --- | --- | --- |
| Dependency manifest block | file header | human/agent が読むべき upstream/downstream context。 |
| `dependency_graph.tsv` | `check_dependency_graph.sh --graph-tsv` | normalized manifest edge artifact。 |
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

Generic normalized transport is an input adapter, not a replacement for the
header graph. `dependency_manifest_records.py` validates the current Rust
JSONL envelope and exposes every retained record family plus the derived
`source_universe`. It loads the canonical caller-owned registry artifact and
uses its entries as the sole kind/capability authority. Before immutable
projection it rejects cross-family snapshot mismatches, invalid identity/fact/
pair derivations, endpoints outside the source universe, incomplete
attestation/observation membership, invalid reconciliation partitions, and
source-content provenance mismatches, even when summary counts and the body
fingerprint were refreshed. It does not infer parent paths or materialize
SQLite. Rust performs a raw duplicate-key preflight before JSON value
materialization for registry, source, normalized, and evidence input; evidence
then shares the no-BOM, UTF-8, LF-only, final-LF, and canonical-order byte gate.
Both implementations reject a locator string shared by different identities
across repo-path, canonical, or alternate locator fields before resolution.
Only the exact source ID derived from `parent_repo_id` and declaration span path
may represent an absent declaration source, yielding `unresolved_source` while
unknown targets remain transport-invalid.
`dependency_manifest_records.py relation-registry-artifact` produces the
canonical registry handoff from the unchanged AgentCanon fixture. The
two-phase `bind_r2_scope.py` evidence boundary is separate: the manifest fixes
the pre-review source/fixture/registry set and closeout later re-hashes every
bound input before verifying exactly one canonical decision and manifest-ID
line in each of two distinct review artifacts. Exit 21 with no output applies
to missing, stale, mismatched, malformed, aliased, or content-identical
bindings. Manifest generation first validates the exact canonical registry
artifact rather than trusting a supplied fingerprint string.

## Import Mapping

| Manifest artifact | DB table | Required fields |
| --- | --- | --- |
| TSV `source` / `target` path | `deps.artifacts` | `artifact_id`, `path`, `kind`, `content_hash` if available |
| TSV edge row | `deps.dependency_edges` | `direction`, `kind`, `source_artifact_id`, `target_artifact_id`, `reason` |
| code import/include/source row | `deps.code_edges` | `language`, `kind`, `source_artifact_id`, `target_locator`, `symbol` |
| graph checker finding | `deps.header_checks` and `report.findings` | `checker`, `status`, `finding_json`, `classification` |
| normalized Rust JSONL record | `deps.artifacts` plus adapter payload | `record_type`, `record_id`, `snapshot_id`, canonical `payload`, source/provenance hash |
| normalized aggregate projection | `deps.artifacts` / parent-owned materialization input | all Rust families, `surface_relations`, and derived `source_universe`; no inferred parent state |

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
