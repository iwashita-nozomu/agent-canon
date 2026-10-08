# Canonical Skill Registry

<!--
@dependency-start
contract agent-runtime
responsibility Points readers to the public skill registry and internal routine registry.
upstream design README.md canonical workflow index
upstream design ../skills/README.md public skill surface contract
upstream design ../internal-routines/README.md internal routine registry
upstream design ./CLI_ENTRYPOINTS.md logical command execution boundary
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
| Git-distributed adapter | `.codex/personal/skills/<skill>/SKILL.md`; authored from the catalog and committed with source changes |
| Installed AgentCanon entry | `~/.agents/skills/<skill>/SKILL.md`, through the bootstrap-managed directory link |
| Repository-owned skill | `.agents/skills/<skill>/SKILL.md` in the owning repository or subtree |

[Codex skill discovery](https://developers.openai.com/codex/skills/) scans
`.agents/skills` from the working directory to the repository root and the user
`~/.agents/skills` directory; it supports symlinked skill folders. AgentCanon's
[bootstrap lifecycle](../../README.md#source-and-artifact-boundary) owns the
user directory link when the explicit control root is `$HOME`. Isolated
`codex prepare` / `codex launch` use a single `CODEX_HOME/skills/agent-canon`
directory link to the same distribution. Normal Git updates do not regenerate
skills, replace the directory, or recreate an already-correct link. Runtime alignment still checks canonical docs,
catalog IDs, and generated adapters for parity.

Read the selected session's registered `SKILL.md` under the active instruction
hierarchy. Use [Owner-First Read Trace](../skills/agent-orchestration.md#owner-first-read-trace)
to locate the canonical owner and the delegated sections relevant to the
current decision; the trace does not replace higher-priority reading
requirements. Resolve adapter-relative links from the adapter's real file
directory, not the product working directory. Only after a read failure inspect
that entry's link target and generated state through the existing bootstrap
owner; do not substitute a same-named file from another checkout. Explicit
source maintenance edits the canonical owner in the selected development
checkout.

An adapter's “Read the canonical owner” instruction uses that same point-of-use
boundary: open the owner's Reader Map or short common conditions, then the selected
section. The thin adapter is a pointer, not a second copy of branch policy.
Its advertised Python command is a logical command packet, not a new Host entrypoint.
Before executing it, use [Tool commands](CLI_ENTRYPOINTS.md#tool-commands) through
[the Host entrypoint](CLI_ENTRYPOINTS.md#host-entrypoint), retaining the current
registered target and existing source-root resolution. A resolved execution route
is reused; this reference does not request installation, setup, or a status probe.

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

### Skill authoring and revision

Use the host-provided `$skill-creator` for general skill authoring and
refactoring. Revise instructions from observed task outcomes: explain the reason
for a consequential constraint, generalize a failure across nearby cases, and
remove directions that do not change a decision or result. Preserve real
authority, safety, compatibility, and completion boundaries. Let the current
task's dependencies and evidence determine order, branches, and parallel work;
do not impose a universal task pipeline. Codex already supplies the authoring
capability, so AgentCanon does not add a second creator or evaluator.

This approach adopts the outcome-based test-and-refine guidance in
[Anthropic's skill-creator revision](https://github.com/anthropics/skills/commit/b0cbd3df1533b396d281a6886d5132f623393a9c)
and [its March 2026 write-up](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills),
while keeping AgentCanon's catalog, generated adapters, and runtime boundaries
with their existing owners.
