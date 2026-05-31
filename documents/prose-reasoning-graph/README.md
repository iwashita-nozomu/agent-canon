<!--
@dependency-start
responsibility Documents the Prose Reasoning Graph canon document set.
upstream design ../README.md AgentCanon document index
downstream design dsl-spec.md normative DSL and graph contract
downstream design ../tools/prose_reasoning_graph.md tool usage documentation
downstream design ../../agents/skills/prose-reasoning-graph.md skill handoff contract
downstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current MVP implementation
@dependency-end
-->

# Prose Reasoning Graph

This directory is the AgentCanon source of truth for Prose Reasoning Graph
concepts that are larger than one tool invocation. Tool usage stays under
`documents/tools/`; the graph language, validation rules, and extension
contract live here.

## Canon Documents

- [DSL Specification](dsl-spec.md): the normative graph/DSL contract for the
  SQLite-backed MVP and later independent tool extraction.

## Ownership Boundary

- This directory owns the Prose Reasoning Graph DSL vocabulary and validation
  contract.
- `documents/tools/prose_reasoning_graph.md` owns CLI usage and operator flow.
- `agents/skills/prose-reasoning-graph.md` owns skill selection, handoff, and
  authority boundaries.
- `tools/agent_tools/prose_reasoning_graph.py` owns the current MVP
  implementation and must be kept in sync with the DSL spec.

## Expansion Rule

When the graph language grows, add narrowly owned documents in this directory
instead of expanding tool usage docs into a second specification. Examples of
valid future documents are adapter contracts, projection algorithms,
diagnostic-rule inventories, or code/design mirror contracts.
