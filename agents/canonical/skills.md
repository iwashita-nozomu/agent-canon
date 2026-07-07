# Canonical Skill Registry

<!--
@dependency-start
contract agent-runtime
responsibility Points readers to the public skill registry and internal routine registry.
upstream design README.md canonical workflow index
upstream design ../skills/README.md public skill surface contract
upstream design ../internal-routines/README.md internal routine registry
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates official system skill delegation
@dependency-end
-->

Public skill purpose, routing, and discovery paths are catalog-backed in
[`../skills/README.md`](../skills/README.md) and
[`../skills/catalog.yaml`](../skills/catalog.yaml).

Workflow-routed review, validation, and compatibility routines live in
[`../internal-routines/README.md`](../internal-routines/README.md).

Runtime alignment enforces that public skill docs, catalog IDs, and
`.agents/skills/*/SKILL.md` shims stay in parity.
Parent-repo-specific skills use the separate project-owned
`.codex/project-skills/<skill>/SKILL.md` lane documented in
`../skills/README.md` and are enabled through parent-owned
`.codex/project-config.toml`; they do not enter the AgentCanon public catalog
unless promoted to shared canon.

Naming carries the visibility boundary:

- Public, user-facing skills use plain hyphen-case and appear in the public
  catalog.
- Runtime-internal skill shims use a leading underscore in
  `.agents/skills/_<name>/SKILL.md` and are owned by the workflow, role, routine,
  or public skill that calls them.
- Workflow-only routines live in `../internal-routines/` as Markdown routines
  rather than Codex skill shims.

## Official System Skill Delegation

Host-provided Codex skills remain outside the AgentCanon public catalog. The
local registry routes to these names and records repo-specific evidence.

| Official System Skill | Owner Boundary |
| --- | --- |
| `$openai-docs` | OpenAI / Codex current product source route. |
| `$skill-creator` | General Codex skill authoring and refactor guidance. |
| `$skill-installer` | Curated and external skill installation. |
| `$imagegen` | Generated bitmap assets. |
| `$plugin-creator` | Codex plugin scaffolding and marketplace metadata. |
