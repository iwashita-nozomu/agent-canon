<!--
@dependency-start
contract tool
responsibility Defines internal AgentCanon tool placement areas.
upstream design ../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md shared tool family ownership and migration policy
downstream implementation ../agent_tools/tool_catalog.py validates effective tool audience and placement
@dependency-end
-->

# Internal Tool Areas

This directory is the target home for helper code that should not be advertised
as a stable user command. The existing runtime still calls many helpers through
their historical paths; move one helper family at a time only after preserving
the catalog entry, tests, docs, and workflow callers.

Use these placement buckets:

- `skills/`: helpers owned by one or more skills.
- `workflows/`: task-start, closeout, routing, run-bundle, and workflow gates.
- `compatibility/`: legacy wrappers kept only to preserve old callers.

The catalog field `placement` is the mechanical source of truth. Directory
names are migration targets, not an excuse to duplicate tool implementations.
