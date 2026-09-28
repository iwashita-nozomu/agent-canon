# Canonical Skill Registry

<!--
@dependency-start
contract agent-runtime
responsibility Points readers to the public skill registry and internal routine registry.
upstream design README.md canonical workflow index
upstream design ../skills/README.md public skill surface contract
upstream design ../internal-routines/README.md internal routine registry
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates official system skill delegation
@dependency-end
-->

Public skill purpose, routing, and discovery paths are catalog-backed in
[`../skills/README.md`](../skills/README.md) and
[`../skills/catalog.yaml`](../skills/catalog.yaml).

Workflow-routed review, validation, and compatibility routines live in
[`../internal-routines/README.md`](../internal-routines/README.md).

## Skill Paths

Keep the canonical source, generated adapter, and Codex discovery entry distinct:

| Responsibility | Path |
| --- | --- |
| AgentCanon source | `agents/skills/<skill>.md` and `agents/skills/catalog.yaml` |
| Ignored generated adapter | `.codex/personal/skills/<skill>/SKILL.md`; not a native discovery root or a hand-edit target |
| Installed AgentCanon entry | `~/.agents/skills/<skill>/SKILL.md`, through the bootstrap-managed directory link |
| Repository-owned skill | `.agents/skills/<skill>/SKILL.md` in the owning repository or subtree |

[Codex skill discovery](https://developers.openai.com/codex/skills/) scans
`.agents/skills` from the working directory to the repository root and the user
`~/.agents/skills` directory; it supports symlinked skill folders. AgentCanon's
[bootstrap lifecycle](../../README.md#source-and-artifact-boundary) owns the
user directory link when the explicit control root is `$HOME`. Isolated
`codex prepare` / `codex launch` remain with that lifecycle, not a guessed global
path or a second registry. Runtime alignment still checks canonical docs,
catalog IDs, and generated adapters for parity.

Read the selected session's registered `SKILL.md` first, then its canonical
owner. Resolve the adapter's relative links from its real file directory, not
the product working directory. Only after a read failure inspect that entry's
link target and generated state through the existing bootstrap owner; do not
substitute a same-named file from another checkout. Explicit source maintenance
edits the canonical owner in the selected development checkout.

Naming carries the visibility boundary:

- Public, user-facing skills use plain hyphen-case and appear in the public
  catalog.
- Runtime-internal skill shims use a leading underscore in
  `.codex/personal/skills/_<name>/SKILL.md` and are owned by the workflow, role, routine,
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
