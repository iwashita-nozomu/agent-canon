<!--
@dependency-start
contract reference
responsibility Defines code dependency analysis scope for the structured analysis package.
upstream design README.md structured analysis package index
upstream design database-design.md defines SQLite tables and DB artifact placement
upstream design ../design/dependency-manifest-design.md separates code dependency evidence from manifest graph evidence
upstream implementation ../../tools/analysis/code/lsp_code_analysis.py extracts canonical LSP code facts
upstream implementation ../../tools/analysis/dependencies/scan_code_dependencies.sh launches bounded queries against selected SCIP evidence
downstream design dependency-header-analysis.md joins code evidence with report trace without merging edge semantics
@dependency-end
-->

# Code Analysis Adapter

この文書は、point LSP facts と optional SCIP reference evidence の境界を
structured analysis に取り込む際の adapter contract として定義する。現在の
SCIP query は external `index.scip` から bounded evidence を返すだけであり、
この package の `deps.code_edges` や persistent graph mirror へ ingest しない。

## Reader Map

- Owns code dependency analysis scope for the structured-analysis package.
- Main path: Scope, Boundary, Import Mapping, Report Trace, and evidence limits.
- Read this before joining code evidence with dependency-manifest evidence.
- Boundary: code dependency edges and manifest edges may be joined for
  explanation, but their meanings stay distinct.

## Scope

Point code analysis uses LSP 3.17 JSON-RPC through
`lsp_code_analysis.py analyze --format json`; it remains distinct from
dependency-header evidence. Repository-wide symbol/reference evidence is an
optional native SCIP index/query path selected through
`scip_index.py` and the bounded Change Impact consumer. The compatibility
`scan_code_dependencies.sh` launcher accepts a selected standard index; it does
not scan source syntax or invoke LSP.

Canonical report schema は `agent-canon.lsp-code-analysis.v1` である。report は
root-relative POSIX locator、UTF-16 position、language server record、capability
matrix、symbols、relations、diagnostics、lexical candidates、lifecycle/status、
provenance を deterministic order で保持する。required
`documentSymbolProvider` が失敗した report は部分的な成功として扱わず、
typed error として返す。optional definition/references/call hierarchy/diagnostics
は `supported_facts`、`supported_empty`、`unsupported` のいずれかを記録する。
server executable は devcontainer manifest の
`resolve_verified_executable` と receipt/live verification を通った absolute path
だけを受け付ける。caller override は absolute executable として provenance に残り、
ambient PATH discovery は code analysis の実行経路にならない。

The selected native SCIP producers currently cover Python when the project
owner supplies its environment input and C/C++ when the build owner supplies a
compile database. Shell and Rust have no selected producer. These capability
limits are not negative reference results; query output is bounded and does not
claim source freshness or call-graph completeness.

## Evidence And Assumption Ledger

- Evidence sources: [documents/structured-analysis/code-analysis.md](code-analysis.md) owns this scope.
- Evidence sources: `tools/analysis/code/lsp_code_analysis.py` owns the LSP adapter and report.
- Evidence sources: `bootstrap/container/image/dependencies.toml` and [documents/design/dependency-manifest-design.md](../design/dependency-manifest-design.md) provide manifest, receipt, and live-verification evidence.
- Evidence sources: `tests/agent_tools/test_lsp_code_analysis.py`, `tests/agent_tools/test_dependency_manifest_tools.py`, `tests/agent_tools/test_search.py`, and `tests/agent_tools/test_git_dependency_diff_summary.py` cover protocol, scanner, consumer, and summary behavior.
- Assumptions: the manifest receipt/live verifier is the authority for executable selection.
- Assumptions: LSP 3.17 server responses are runtime evidence.
- Assumptions: selected SCIP artifacts are reference evidence, not proof of
  current source bytes, compiler completeness, or caller/callee relations.
- Assumptions: unindexed and unsupported targets are reported as capability
  gaps, not empty-reference proof.
- Parent-doc alignment: [documents/design/dependency-manifest-design.md](../design/dependency-manifest-design.md) owns manifest/dependency evidence.
- Parent-doc alignment: [documents/tools/lsp_code_analysis.md](../tools/lsp_code_analysis.md) owns the tool and report contract.
- Parent-doc alignment: [documents/tools/search-coordination.md](../tools/search-coordination.md) owns the in-memory `code-deps` consumer boundary.

## Boundary

次を分ける。

| Evidence family | Meaning | Storage owner |
| --- | --- | --- |
| Dependency manifest graph | 人間/agent が読むべき design、implementation、environment context。 | `deps.dependency_edges` |
| Code dependency evidence | Point LSP report or bounded SCIP index/query facts. SCIP remains an external standard artifact; it is not stored in this package's graph tables. | External runtime artifact |
| Prose reasoning graph | source text anchor と claim/evidence/discourse relation。 | `prose.nodes`, `prose.edges` |
| Report contract graph | report root から claim、evidence、finding、action への trace。 | `report.*` |

Manifest edge と code evidence を同じ relation として扱うと、「読む context」と「source
symbol/reference evidence」が混ざる。Any selected report may link them for explanation,
but this adapter does not import SCIP occurrences into a second graph.

## Import Mapping

This package has no current SCIP-to-database importer. Preserve the native
index path/hash and bounded query output as external evidence references; do
not materialize the full index or infer `deps.code_edges` rows from it.

## Report Trace

Selected code evidence may support review of a design/implementation boundary;
it does not establish a complete mirror or populate a persistent relation graph.

```text
report.claims.claim_id
  -> report.evidence_refs.target_id = artifact:code-file
  -> external SCIP index/query artifact (when selected)
  -> dependency-header evidence (kept as a separate relation family)
  -> prose/source anchors that explain the design
```

この trace により、「設計文書で主張した module boundary が、実装 import/include と
dependency header の両方で支えられているか」を検証できる。

The bounded SCIP query reports unsupported and unindexed targets through its
existing status/capability fields. This package does not emit code-edge
diagnostics from that projection. Empty or omitted rows must not be interpreted
as evidence that a source relationship is absent.
