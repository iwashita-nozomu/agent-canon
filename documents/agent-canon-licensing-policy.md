# AgentCanon Licensing Policy
<!--
@dependency-start
contract policy
responsibility Documents AgentCanon licensing ownership and parent-repository boundary.
upstream design ../LICENSE AgentCanon license text
upstream design ./SHARED_RUNTIME_SURFACES.md shared surface ownership policy
upstream design ../vendor/README.md third-party vendor policy
downstream design ./shared-runtime-surfaces.toml classifies parent-repository license surfaces
@dependency-end
-->

AgentCanon is licensed under Apache License 2.0.

The license boundary is explicit:

- `vendor/agent-canon/LICENSE` covers AgentCanon-owned runtime, workflow, skill,
  subagent, MCP, tool, and shared documentation surfaces.
- Parent repository code, experiments, Docker runtime, project documents, and
  root `LICENSE` remain parent-owned unless they are symlink or synced-copy views
  of AgentCanon surfaces.
- Root symlink views into AgentCanon retain the AgentCanon license; editing the
  root view does not create a new parent-repository license surface.
- Template or derived repositories may set a different root project license, but
  they must keep AgentCanon's license with the submodule.
- Third-party skills or assets in AgentCanon's internal `vendor/` directory
  (`vendor/agent-canon/vendor/` when viewed from a parent repository) must
  record upstream URL, revision, and license metadata before they are enabled.
- Devcontainer-installed local LLM tooling is not vendored into the repository.
  llama.cpp is an external MIT-licensed tool fetched into `~/.tools`, and the
  default SmolLM3-3B GGUF model is an external Apache-2.0 model fetched
  lazily by llama.cpp cache behavior. Do not commit those binaries or model
  weights.

When adding a new shared surface, update the dependency header, the surface
manifest if the path is exposed to parent repositories, and any README section
that tells users whether the surface belongs to AgentCanon or to the parent repo.
