<!--
@dependency-start
contract reference
responsibility Documents dependency manifest graph report rendering.
upstream implementation ../../tools/analysis/dependencies/render_dependency_manifest_graph.py renders Markdown and DOT graph reports.
upstream design ../design/dependency-manifest-design.md defines dependency manifest semantics.
upstream design ../structured-analysis/graph-dsl.md defines shared graph storage and projection contract.
upstream design ../prose-reasoning-graph/dsl-spec.md defines prose graph adapter vocabulary when dependency graph views are embedded in prose workflows.
downstream implementation ../../tests/agent_tools/test_render_dependency_manifest_graph.py tests renderer behavior.
@dependency-end
-->

# render_dependency_manifest_graph.py

Use this tool when a review needs a repo-local dependency-manifest graph artifact.

## Reader Map

- Owns: CLI and output contract for dependency manifest bundle creation and named
  projection mode.
- Reads: one canonical dependency query through `GraphClient`.
- Produces: full/changed bundle routes, named projections, manifest and Graph IR
  schema commitments, and self-contained HTML behavior.
- Produces native Graph IR, Markdown/Mermaid, DOT, HTML, and bundle manifest
  artifacts with source labels, relations, hashes, and final-output checks.

## Skill / Evaluator Bundle Route

Skill and evaluator execution selects one of these two bundle commands. The
first covers the full repository and the second filters the canonical query to
the current change set.

```bash
python3 tools/analysis/dependencies/render_dependency_manifest_graph.py \
  --root . \
  --scope full \
  --bundle-dir reports/dependency-graph \
  --format json
```

```bash
python3 tools/analysis/dependencies/render_dependency_manifest_graph.py \
  --root . \
  --scope changed \
  --bundle-dir reports/dependency-graph \
  --format json
```

## Scope and Source

- `--scope` controls the set of nodes/edges the tool accepts as input.
- `full` scope is default.
- `changed` scope is explicit and should be used when reviewing changed graph output.
- The tool always requests
  `graph query --all --relation dependency --direction both --depth 0` with
  profile `default`; there is no supplied-TSV or parser fallback.
- Directional topology cycle diagnostics are renderer observations and do not change the
  manifest checker status.
- Canonical source provenance is normalized in `source.root` and recorded in the
  manifest.
- Full evidence output is emitted without fixed artifact-count caps.

## Graph Abort Semantics

- A valid non-fresh graph response forwards its status, diagnostics, and exit
  code and aborts output generation.
- Launch, executable, JSON, schema, or endpoint/detail-join failure is a
  consumer error. It does not emit a generated bundle and is a hard stop
  for this route.
- Renderer topology diagnostics are observational and do not define checker pass/fail.

## Graph IR Evidence Contract

The canonical graph fact is the source-truth anchor for every rendered row.
Each node record preserves its source span, and each edge record preserves the
typed relation, producer, authority, and evidence reference supplied by the
graph query. The renderer lowers that graph into a lower text unit without
inventing relations or re-parsing dependency headers.

The Graph IR `nodes` table and `edges` table are projection views over those
records. Their `payload_json` values retain graph-owned provenance so a derived
projection or reader-state filter can be traced back to the same source fact.
An embedded prose workflow may summarize a macro-claim, but it cannot promote
that summary into a new graph edge.

## Bundle Outputs

Bundle mode requires `--bundle-dir` and emits:

- `dependency_graph.tsv`
- `dependency_graph.ir.json`
- `dependency_graph.md`
- `dependency_graph.dot`
- `dependency_graph.html`
- `manifest.json`

The bundle command emits deterministic outputs; each artifact descriptor includes a
`sha256` digest, byte size, and media type, with full evidence retention for a
single invocation.

`manifest.json` contains stable, bundle-local locators and deterministic hashes:

- `artifacts[].path`: stable locator path relative to `--bundle-dir`
- `artifacts[].sha256`: digest for generated outputs
- `artifacts[].bytes`: exact byte size of each artifact
- `schema`, `status`, `scope`, `source`, `checker`, and `summary`: native graph metadata

The renderer validates source checker results, preserves requested nodes and
relations with their labels and provenance, formats selected outputs, and reads
back final artifact bytes. It does not construct a private universe, ToolCall
packet, coverage marker, count map, or digest gate.

Rendered output is emitted as bundle text and JSON:
- bundle text at Markdown and DOT outputs
- bundle JSON at `dependency_graph.ir.json` and `manifest.json`

The bundle command fails fast on broken inputs (`fail-on-broken`) and does not
partial-write to an existing path on hard failure.

## Named Output Projections

This direct CLI mode is outside the exact-three skill/evaluator route.

Projection mode omits `--bundle-dir` and requires at least one of:

- `--ir-out`
- `--markdown-out`
- `--dot-out`
- `--html-out`

When provided, only requested output files are rendered.

## Manifest / Artifact Contract

- Manifest schema: `agent_canon.dependency_graph_bundle.v1`.
- Manifest fields:
  - `schema`
  - `status`
  - `scope`
  - `source`
  - `checker`
  - `summary`
  - `artifacts`
- Manifest status for successful generated bundles is `pass`.
- Checker status is the canonical graph status and is `fresh` for a successful
  projection.
- `manifest.json` uses UTF-8, LF, sorted-key indented JSON.
- Artifact descriptors in manifest include `path`, `media_type`, `bytes`, and `sha256`.

The Graph IR schema is `agent_canon.graph_ir.v2`. Its `documents` records source
projections, `metadata` records deterministic producer and checker context, and
`diagnostics` records renderer observations. Directional cycles are represented
as separate `cycles.upstream` and `cycles.downstream` arrays.

## Final-artifact readback order

After native TSV parsing, the renderer computes directory containment and
retains provenance for each emitted GraphIR directory and containment edge. It
then performs this order for each selected artifact:

1. commit renderer syntax/layout at the formatter-owned final-write boundary;
2. read back final bytes/path;
3. verify syntax, labels, relation endpoints, source provenance, artifact
   descriptors, and requested output paths.

TSV remains byte-for-byte producer evidence and checker authority. It is copied
or generated transactionally and retained in artifact descriptors. Formatter
ownership remains syntax/layout-only and cannot extract, delete, aggregate, or
relabel source identities.

この順序では `source read/capture before output mutation` を必須とします。
canonical graph status/query と generated TSV capture が完了するまで、repository
tree の出力先、親ディレクトリ、staging directory を作成・変更しません。generated
TSV は `temporary graph input outside root` として system temp 領域に置きます。
bundle mode はその capture 後に target parent/staging transaction を開始し、
staged `dependency_graph.tsv` へ copy します。supplied TSV の identity と atomic
output publication の契約は維持します。

## HTML Behavior

- Rendered HTML is a single in-file workbench with static graph/table evidence and
  inline interaction script.
- The native SVG and node/edge tables are complete evidence channels. Directory
  module rows and containment-edge rows are complete in their dedicated tables;
  source IDs, endpoints, kinds, and full paths must agree across duplicate
  channels.
- Offline readback rejects external/resource-bearing HTML attributes, CSS
  `url()`/`@import`, and executable JavaScript network/import APIs. URLs or
  network-looking words in graph JSON, visible labels, comments, ordinary
  strings, or template text are data and do not fail the resource graph.
- No external network requests, browser installation, npm package, or DOM shim
  is used by the checker.
- IR is embedded in-page via JSON script for inspector/filter parity.
- Keyboard entry for interactive controls follows standard activation parity with
  pointer behavior and explicit focus semantics.
- The inline `buildAdjacency`/`graphNeighborhood`/`visibleModel` region is pure
  model logic. It returns the complete selected node/edge model and has no
  silent fixed-cap or truncation branch; the Node `vm` harness exercises its
  default, query, focus/depth, and direction/kind filter states.

## CLI and Reference

```bash
python3 tools/analysis/dependencies/render_dependency_manifest_graph.py \
  --root . \
  --ir-out reports/dependency_graph.ir.json \
  --markdown-out reports/dependency_graph.md \
  --dot-out reports/dependency_graph.dot \
  --html-out reports/dependency_graph.html
```
