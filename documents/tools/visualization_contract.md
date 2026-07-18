<!--
@dependency-start
contract tool
responsibility Documents the exact D2.4 seven-function executable typed visualization contract owner.
upstream implementation ../../tools/agent_tools/visualization_contract.py typed contract, ToolCall, marker, readback, and checker owner
downstream implementation ../../tests/agent_tools/test_visualization_contract.py exact contract coverage tests
downstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py dependency artifact adapter
@dependency-end
-->

# visualization_contract.py

`visualization_contract.py` is the single exact typed implementation module for
the sole public `code-visualization` owner. Renderers remain syntax/layout
adapters and cannot define a smaller universe, local omission policy, or local
pass/fail contract.

## Exact public types

The module defines the D2.4 aliases `JsonScalar`, `JsonValue`,
`SourceItemKind`, `SourceItemOrigin`, `ArtifactFormat`, `ManifestStatus`,
`FilterMode`, `ViewState`, `ToolID`, `ArgumentSchemaID`, and `ViolationCode`.
It defines these exact records:

- `FilterRecord`
- `VisualizationSourceItem`
- `VisualizationSourceUniverse`
- `ProjectionCoverageEntry`
- `ProjectionCoverageManifest`
- `CoverageViolation`
- `CoverageReport`
- `ReadbackProjection`
- `ToolCall`
- `CoverageArguments`
- `DependencyManifestArguments`
- `AlgorithmFlowchartArguments`
- `DocumentMermaidArguments`
- `RepositoryGraphArguments`
- `KnowledgeGraphArguments`

Every source, rendered, and readback count map has exactly the eight kinds
`identity`, `edge`, `field`, `phase`, `branch`, `module`, `evidence`, and
`time`. Violations and identity lists are complete and untruncated.

## Seven public functions

```python
build_source_universe(...) -> VisualizationSourceUniverse
build_projection_coverage_manifest(...) -> ProjectionCoverageManifest
validate_projection_coverage(..., readback=...) -> CoverageReport
serialize_tool_call(tool_call: object) -> str
serialize_projection_identity(identity: str) -> str
serialize_projection_coverage_manifest(
    manifest: ProjectionCoverageManifest,
    *,
    owner_tool_call: ToolCall,
    adapter_tool_call: ToolCall,
) -> str
readback_projection(...) -> ReadbackProjection
```

No adapter, renderer, skill, workflow, or external test calls an
underscore-prefixed owner helper. `serialize_projection_identity` is the sole
artifact-locator serializer. `serialize_projection_coverage_manifest` validates
the complete passing manifest and the canonical owner-first, adapter-second
ToolCall pair before returning the marker.

`build_source_universe` accepts explicit literal-request, owner-closure, and
dependency-closure buckets. It validates canonical payload JSON, exact origins,
source offsets, ordinals, global IDs, and view-only filters before sorting by
the D2.3 identity order and computing `source_fingerprint`.

`build_projection_coverage_manifest` accepts an external
`ReadbackProjection`, retains one entry per source identity, emits all three
eight-kind count maps, and records all omissions and violations.
`validate_projection_coverage` compares the universe, manifest, and final
artifact readback without truncating failures.

## Canonical ToolCalls

| Role | `tool_id` | `argument_schema` |
| --- | --- | --- |
| owner | `agent_canon.visualization.coverage` | `agent_canon.visualization.arguments.coverage.v1` |
| dependency adapter | `agent_canon.visualization.adapter.dependency_manifest` | `agent_canon.visualization.arguments.dependency_manifest.v1` |
| algorithm adapter | `agent_canon.visualization.adapter.algorithm_flowchart` | `agent_canon.visualization.arguments.algorithm_flowchart.v1` |
| document adapter | `agent_canon.visualization.adapter.document_mermaid` | `agent_canon.visualization.arguments.document_mermaid.v1` |
| repository adapter | `agent_canon.visualization.adapter.repository_graph` | `agent_canon.visualization.arguments.repository_graph.v1` |
| knowledge adapter | `agent_canon.visualization.adapter.knowledge_graph` | `agent_canon.visualization.arguments.knowledge_graph.v1` |

The executable path
`tools/agent_tools/render_dependency_manifest_graph.py` is a command and is
never a ToolCall ID. `serialize_tool_call` validates the paired schema, exact
shared fields, adapter locator fields, JSON types, and absence of unknown fields
before emitting canonical UTF-8 JSON. Non-mappings, missing/extra top-level
keys, wrong top-level types, unhashable ToolIDs, wrong argument types, and
unknown extra arguments produce deterministic `invalid_tool_call:<field>`;
schema mismatches produce `schema_mismatch:<field>`.

## Final-artifact readback

Every artifact marker begins with
`agent_canon_visualization_coverage_v1:` and contains URL-safe unpadded base64
of canonical manifest JSON. Readback occurs after formatter ownership:

- TSV reads `<artifact_id>.coverage.json` and scans sibling
  `<artifact_id>.tsv`.
- GraphIR v2 reads `visualization_coverage` and then scans listed tokens.
- Markdown/Mermaid requires one adjacent HTML comment and one Mermaid fence.
- DOT requires the graph comment marker.
- HTML requires
  `script[type=application/json][id=agent-canon-visualization-coverage]`.

The marker alone never passes. `readback_projection` scans every listed final
syntax token, reconstructs one-to-one identities and eight-kind counts, detects
orphan identities, and computes the readback digest. Missing sidecars, markers,
tokens, malformed payloads, and artifact mismatches return typed failure
records rather than partial success.

For `renderer_id = agent_canon.visualization.adapter.algorithm_flowchart`,
canonical Markdown readback also requires exactly one Mermaid diagram and no
Markdown table outside fences. It returns typed `diagram_count_mismatch` or
`table_fallback` violations. Rust formatting owns Mermaid syntax only.
