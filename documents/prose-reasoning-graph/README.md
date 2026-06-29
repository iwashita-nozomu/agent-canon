<!--
@dependency-start
contract reference
responsibility Documents the Prose Reasoning Graph canon document set.
upstream design ../README.md AgentCanon document index
upstream design ../structured-analysis/README.md structured analysis package boundary
upstream design ../structured-analysis/graph-dsl.md shared Graph DSL Core storage contract
downstream design dsl-spec.md normative DSL and graph contract
downstream design ../tools/prose_reasoning_graph.md tool usage documentation
downstream design ../../agents/skills/prose-reasoning-graph.md skill handoff contract
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current MVP implementation
@dependency-end
-->

# Prose Reasoning Graph

This directory owns the prose adapter/profile for AgentCanon graph analysis.
The shared storage language lives in
[Graph DSL Core](../structured-analysis/graph-dsl.md). Tool usage stays under
`documents/tools/`; prose-specific source anchoring, discourse relations,
projection rules, validation rules, and extension contract live here.

## Canon Documents

- [DSL Specification](dsl-spec.md): the prose adapter/profile contract over the
  shared Graph DSL Core.

## Ownership Boundary

- This directory owns prose graph vocabulary and validation contract.
- Generic graph storage object families, layer registry, and contract
  validation belong to [Graph DSL Core](../structured-analysis/graph-dsl.md).
- The broader extraction-oriented package boundary lives in
  [Structured Analysis](../structured-analysis/).
- The DSL treats prose as one text-anchored semantic graph; macro prose
  structure is a derived projection view, not a second source graph.
- Derived projection views may recommend prose, list, table, figure, or
  equation renderings only through materialized `presentation` feature nodes and
  `has_feature` edges attached to source anchors. The recommendation remains a
  verified presentation candidate, not a replacement for the canonical source
  graph.
- Corpus hints may be inferred from source text and user prompt, then exported
  as projection metadata for retrieval and evaluation calibration.
- `documents/tools/prose_reasoning_graph.md` owns CLI usage and operator flow.
- `agents/skills/prose-reasoning-graph.md` owns skill selection, handoff, and
  authority boundaries.
- `tools/agent_tools/prose_reasoning_graph.py` owns the current MVP
  implementation and must be kept in sync with the DSL spec.

## Expansion Rule

When the graph language grows, add specifically owned documents in this directory
instead of expanding tool usage docs into a second specification. Examples of
valid future documents are adapter contracts, projection algorithms,
diagnostic-rule inventories, or code/design mirror contracts.
