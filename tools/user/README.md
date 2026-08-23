<!--
@dependency-start
contract tool
responsibility Defines the stable user-facing AgentCanon tool entrypoint area.
upstream design ../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md shared tool family ownership and migration policy
downstream implementation ../agent_tools/tool_catalog.py validates effective tool audience and placement
@dependency-end
-->

# User Tool Entrypoints

This directory is the target home for stable commands that a repository user or
parent-session agent may run directly from the repo root. Existing commands are
not moved here until their catalog entry, tests, docs, and workflow callers have
been updated in the same change.

The live classification source is `tools/catalog.yaml`:

- `audience: user` means the command is an intended public entrypoint.
- `placement: user_entrypoint` means the command may eventually live under
  this directory or expose a thin wrapper here.

Compatibility paths stay in their historical locations until every documented
caller has migrated. Do not put skill-private helpers here.
