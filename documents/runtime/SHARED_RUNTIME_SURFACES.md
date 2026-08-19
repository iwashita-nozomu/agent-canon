<!--
@dependency-start
contract reference
responsibility Documents the explicitly selected live AgentCanon integration surfaces.
upstream design ../contracts/static-seed-export.md default source-free consumer boundary
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace boundary
downstream design ./shared-runtime-surfaces.toml machine-readable opt-in projection manifest
downstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
downstream implementation ../../tools/agent_tools/surface_manifest.py parses the opt-in manifest
downstream implementation ../../tools/sync_agent_canon.sh enforces explicitly selected root-view synchronization
downstream implementation ../../tools/agent_tools/check_convention_compliance.py verifies manifest/doc wiring
@dependency-end
-->

# Shared Runtime Surfaces

This document owns the named **`live-agent-canon` explicit opt-in integration**.
It does not make AgentCanon source, tools, tests, or update state part of every
repository. A consumer selects this mode only when its Codex session must read
AgentCanon-owned instructions, project configuration, custom agents, or hooks
from an exact AgentCanon source pin.

The machine-readable source of truth is
`documents/runtime/shared-runtime-surfaces.toml`. It records
`integration_mode = "live-agent-canon"`, `default_consumer = false`, and
`selection = "explicit-opt-in"`. The default static consumer remains a separate
contract until its producer-side retirement is completed; it must not silently
consume this live manifest.

## Selection Boundary

| Mode | AgentCanon checkout | Codex repository view |
| --- | --- | --- |
| Static consumer | not required | consumer-owned regular files under its own contract |
| `live-agent-canon` | exact reviewed pin required before Codex activation | manifest-owned root symlinks |

Normal product build, test, documentation, Docker, and CI commands remain
parent-owned. They may validate the lexical view and exact gitlink without
initializing the AgentCanon checkout. Loading AgentCanon custom agents and hooks
requires the explicitly initialized exact pin; no background latest lookup,
credential fallback, or updater is implied.

## Runtime Reachability Model

Let `D` be the paths Codex reads directly and `R(D)` the exact runtime
dependencies named by those declarations. The live root view is:

```text
P = D ∪ R(D)

D = {
  AGENTS.md,
  .codex/config.toml,
  .codex/agents,
  .codex/hooks.json
}

R(D) = {
  .codex/hooks
}
```

`AGENTS.md` supplies the instruction chain. `.codex/config.toml` registers the
project-scoped runtime and custom agents. `.codex/agents` contains the actual
AgentCanon-owned standalone agent definitions. `.codex/hooks.json` declares the
active lifecycle hooks, and `.codex/hooks` is their bounded entrypoint closure.

The hook dispatcher resolves its physical source under the exact
`vendor/agent-canon` checkout and imports implementation modules from that same
pin. Therefore the root does not need a second alias for the AgentCanon tools
tree.

## Projection Metadata

Each `[[surface]]` declares:

- `path`: root-relative view path;
- `mode`: `symlink` for a runtime view or `repo_state` for lifecycle state;
- `source`: path relative to the exact AgentCanon checkout;
- `projection_producer`: owner of the bytes or state;
- `projection_kind`: synchronization category;
- `local_override_allowed`: whether a parent may replace the view; and
- `optional`: whether a lifecycle materializes the entry only when selected.

The parser validates typed selection metadata and renders link specifications
from this manifest. `link-root` and `check` do not maintain a second active-path
list.

## Active Codex Projection

| Root path | Mode | AgentCanon source | Reason |
| --- | --- | --- | --- |
| `AGENTS.md` | symlink | `ROOT_AGENTS.md` | Codex instruction discovery |
| `.codex/config.toml` | symlink | `.codex/config.toml` | project configuration discovery |
| `.codex/agents` | symlink | `.codex/agents` | project custom-agent discovery |
| `.codex/hooks.json` | symlink | `.codex/hooks.json` | project hook discovery |
| `.codex/hooks` | symlink | `.codex/hooks` | hook entrypoint dependency |

`.agent-canon` is optional parent-owned lifecycle state produced by the update
transaction. It is not a Codex discovery surface and is not evidence that the
whole AgentCanon repository tree should be projected.

## Excluded Internal Trees

Codex does not discover generic AgentCanon `tools/**`, `tests/**`, documents,
fixtures, or maintainer checkers merely because they exist in the source
checkout. Those paths remain under the AgentCanon owner and are executed there
when AgentCanon itself is changed.

Root `tools/` is a parent-owned regular container. The former
`tools/agent-canon -> ../vendor/agent-canon/tools` alias is a retired migration
path, not an active runtime surface. The canonical implementation remains under
`vendor/agent-canon/tools/`, and a selected command may address that exact pin
directly. Project-local automation must stay in project-owned paths, and
project-local tests remain project-owned; neither tree is projected from
AgentCanon.

The `removed_legacy` list exists only to clean up known stale AgentCanon
symlinks while preserving regular parent content. It no longer claims the
parent `tests/` directory as AgentCanon state. A missing retired path is already
at the fixed point.

## Editing Rule

Edit AgentCanon behavior in an AgentCanon issue branch based on current
AgentCanon `main`. Edit project product, build, tests, and local policy in the
parent repository. A live consumer tracks only the exact source pin and the
manifest-owned view edges; it does not copy or locally patch AgentCanon custom
agent definitions.

A repository that selected the live mode may repair its views through the
source-root resolver:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
    exec tools/sync_agent_canon.sh link-root
```

`link-root` must preserve parent-owned regular content. It may remove a retired
path only under the existing bounded stale-symlink rules.

## Validation

For AgentCanon source changes:

```bash
python3 -m unittest -v tests/agent_tools/test_codex_projection_boundary.py
python3 tools/agent_tools/surface_manifest.py --root . --prefix . check-doc
```

For an initialized live parent integration:

```bash
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
  exec tools/sync_agent_canon.sh check
```

A parent repository may additionally validate the tracked symlink modes and
lexical targets while the submodule checkout is uninitialized. That structural
check does not claim that Codex can load the target bytes until the exact pin is
initialized.
