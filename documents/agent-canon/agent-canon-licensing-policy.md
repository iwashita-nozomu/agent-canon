# AgentCanon Licensing Policy
<!--
@dependency-start
contract policy
responsibility Documents AgentCanon licensing ownership and parent-repository boundary.
upstream design ../../LICENSE AgentCanon license text
upstream design ../../README.md standalone source and parent boundary
@dependency-end
-->

AgentCanon is licensed under Apache License 2.0.

The license boundary is explicit:

- `LICENSE` covers AgentCanon-owned runtime, workflow, skill,
  subagent, MCP, tool, and shared documentation surfaces.
- Parent repository code, experiments, Docker runtime, project documents, and
  root `LICENSE` remain parent-owned unless they are symlink or synced-copy views
  of AgentCanon surfaces.
- Parent projects consume AgentCanon as a standalone source/runtime capability;
  they do not create root symlink views or pin a submodule.
- Third-party skills or assets in AgentCanon's internal `vendor/` directory must
  record upstream URL, revision, and license metadata before they are enabled.
- Devcontainer-installed third-party tools are not vendored into the
  repository; their licenses remain recorded in the dependency-tool inventory.

When adding a new shared surface, update the dependency header, the surface
manifest if the path is exposed to parent repositories, and any README section
that tells users whether the surface belongs to AgentCanon or to the parent repo.
