<!--
@dependency-start
contract reference
responsibility Documents dependency manifest graph report rendering.
upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT graph reports.
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
