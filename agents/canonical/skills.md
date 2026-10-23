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
Reuse guidance already available in the current model context with the same
source binding; selecting the Skill again does not require reopening it.
Keep reads within the tool's output limit. After truncation, fetch only the
missing relevant range instead of repeating the combined file read. Restore
needed content after compaction when it is no longer in context.
When an owner invokes a tool, use the existing CLI, API, script, or Make entrypoint
through [the Host entrypoint](CLI_ENTRYPOINTS.md#host-entrypoint), passing its
native argv and retaining the current registered target and source-root resolution.
AgentCanon does not materialize a private command packet or binding language before
execution; the existing entrypoint remains responsible for its own arguments and
semantics.

Visibility and naming rules are owned by
[Skill Visibility Naming](../skills/README.md#skill-visibility-naming).
AgentCanon skill maintenance is governed by
[Updating Skills](../skills/README.md#updating-skills).

## Official System Skill Delegation

Host-provided Codex skills remain outside the AgentCanon public catalog. The
local routing table is maintained in
[Official System Skill Delegation](../skills/README.md#official-system-skill-delegation).
General authoring uses the host-provided `$skill-creator`; AgentCanon registration
and distribution use [Updating Skills](../skills/README.md#updating-skills).
