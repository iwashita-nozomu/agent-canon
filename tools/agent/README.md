<!--
@dependency-start
contract tool
responsibility Defines internal AgentCanon tool placement areas.
upstream design ../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md shared tool family ownership and migration policy
downstream implementation ../runtime/manifest/tool_catalog.py validates effective tool audience and placement
@dependency-end
-->

# Internal Tool Areas

This directory contains internal orchestration, skill, and template helpers.
For the implementation being maintained, use its existing owner:

- [Skill helpers](skills/README.md): skill routing, document reading, and materialization.
- [Orchestration](orchestration/): task routing, handoff, team, and review helpers.
- [Templates](templates/): code, bundle, and entrypoint rendering.

Public command identity, audience, and placement remain owned by
[the tool catalog](../catalog.yaml); a directory name does not make an internal
helper a public command. Runtime lifecycle and compatibility implementations
remain at their actual catalog paths, not empty migration-target directories.
