<!--
@dependency-start
contract reference
responsibility Documents dependency manifest graph report rendering.
upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT graph reports.
upstream implementation ../../tools/agent_tools/visualization_contract.py owns projection identity, marker, readback, and coverage semantics.
upstream design ../dependency-manifest-design.md defines dependency manifest semantics.
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
- Reads: repo-local dependency TSV from checker outputs under `check_dependency_graph.sh`
  or a supplied `--graph-tsv`.
- Produces: three canonical bundle routes, named projections, manifest and Graph IR
  schema commitments, and self-contained HTML behavior.
- Produces the exact D2.4 `VisualizationSourceUniverse`, ordered owner/adapter
  `ToolCall` records, and artifact-specific manifest/readback/report records.

## Skill / Evaluator Exact-Three Route

Skill and evaluator execution uses exactly one of these three bundle commands.
The first command covers the full repository, the second covers the current
change set, and the third renders a supplied TSV snapshot.

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --root . \
  --scope full \
  --bundle-dir reports/dependency-graph \
  --format json
```

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --root . \
  --scope changed \
  --bundle-dir reports/dependency-graph \
  --format json
```

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --root . \
  --graph-tsv reports/dependency_graph.tsv \
  --bundle-dir reports/dependency-graph \
  --format json
```

In the supplied route, only the values passed to `--graph-tsv` and
`--bundle-dir` vary.

## Scope and Source

- `--scope` controls the set of nodes/edges the tool accepts as input.
- `full` scope is default.
- `changed` scope is explicit and should be used when reviewing changed graph output.
- `--graph-tsv` accepts an externally supplied TSV snapshot and does not force full scope.
- Directional topology cycle diagnostics are renderer observations and do not change the
  manifest checker status.
- Canonical source provenance is normalized in `source.root` and recorded in the
  manifest.
- Full evidence output is emitted without fixed artifact-count caps.

## Checker Abort Semantics

- `check_dependency_graph.sh` nonzero status means abort output generation.
- A checker failure does not emit a generated bundle and must be treated as a hard stop
  for this route.
- Renderer topology diagnostics are observational and do not define checker pass/fail.

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
- `visualization_source_universe`: native node/edge identities plus every
  GraphIR-derived directory node and containment edge, computed before
  projection with deterministic source provenance
- `visualization_tool_calls`: exactly one canonical owner ToolCall followed by
  exactly one dependency-adapter ToolCall
- `visualization_coverage`: one record per rendered GraphIR,
  Markdown/Mermaid, DOT, and HTML artifact, each containing its
  `ProjectionCoverageManifest`, external
  final-artifact `ReadbackProjection`, and `CoverageReport`

The ToolCall order and exact pairs are:

1. `agent_canon.visualization.coverage` /
   `agent_canon.visualization.arguments.coverage.v1`
2. `agent_canon.visualization.adapter.dependency_manifest` /
   `agent_canon.visualization.arguments.dependency_manifest.v1`

`tools/agent_tools/render_dependency_manifest_graph.py` remains the executable
command path. It is never a ToolCall ID.

`dependency_graph.tsv` remains one of the six basenames and the native
checker/source evidence. It is not a rendered visualization projection and has
no partial full-universe coverage record.

Every coverage report exposes exact eight-kind `source_counts`,
`rendered_counts`, and `readback_counts`, the deterministic `coverage_digest`,
and the complete untruncated violation list. Native nodes map to `identity`,
native and containment edges map to `edge`, and derived directories map to
`module`; the other five fixed kinds remain present with zero counts when the
dependency graph has no such source record.

Rendered output is emitted as bundle text and JSON:
- bundle text at markdown and dot outputs
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
- Checker status is `pass` for checker generated bundles and `not_run` for supplied
  TSV projections.
- `manifest.json` uses UTF-8, LF, sorted-key indented JSON.
- Artifact descriptors in manifest include `path`, `media_type`, `bytes`, and `sha256`.

The Graph IR schema is `agent_canon.graph_ir.v2`. Its `documents` records source
projections, `metadata` records deterministic producer and checker context, and
`diagnostics` records renderer observations. Directional cycles are represented
as separate `cycles.upstream` and `cycles.downstream` arrays.

## Final-artifact marker and readback order

Coverage is not inferred from renderer output. After native TSV parsing, the
adapter computes directory containment and adds every emitted GraphIR directory
node (`kind=module`) and containment edge (`kind=edge`) to the dependency
closure. Each derived payload records
`provenance_kind=derived_directory_containment`, the producer path, its
directory or source/target identity, and all native source identities from
which it was derived. The adapter then performs this order for each of the four
rendered artifacts:

1. serialize the owner ToolCall followed by the dependency adapter ToolCall;
2. build complete one-to-one projection entries using only
   `serialize_projection_identity`;
3. build the typed manifest and obtain its marker only from
   `serialize_projection_coverage_manifest`;
4. commit renderer syntax/layout at the formatter-owned final-write boundary;
5. call `readback_projection` with the final bytes/path;
6. call `validate_projection_coverage(..., readback=...)`.

The exact marker prefix is
`agent_canon_visualization_coverage_v1:`. GraphIR v2 stores a
`visualization_coverage.marker` object; Markdown stores one adjacent HTML
comment immediately before its Mermaid fence; DOT stores a graph comment; HTML
stores `script[type=application/json][id=agent-canon-visualization-coverage]`.
The separate identity tokens are also serialized, so marker presence alone
cannot pass readback.

TSV remains byte-for-byte producer evidence and checker authority. It is copied
or generated transactionally and retained in artifact descriptors, but it does
not receive a coverage sidecar or subset manifest. GraphIR, Markdown, DOT, and
HTML all use the same full native-plus-derived universe and have exactly equal
manifest source-identity sets. Formatter ownership remains syntax/layout-only
and cannot extract, delete, aggregate, or relabel source identities.

## HTML Behavior

- Rendered HTML is a single in-file workbench with static graph/table evidence and
  inline interaction script.
- No external network requests.
- IR is embedded in-page via JSON script for inspector/filter parity.
- Keyboard entry for interactive controls follows standard activation parity with
  pointer behavior and explicit focus semantics.

## CLI and Reference

```bash
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --graph-tsv reports/dependency_graph.tsv \
  --ir-out reports/dependency_graph.ir.json \
  --markdown-out reports/dependency_graph.md \
  --dot-out reports/dependency_graph.dot \
  --html-out reports/dependency_graph.html
```
