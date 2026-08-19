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

The top-level `projection_forbidden_roots` set is a different contract. It
declares AgentCanon standalone source roots that cannot be a projection target,
projection source, legacy-cleanup path, repository state path, or update
transition candidate. It does not make those paths root-absence entries and does
not grant the synchronizer deletion ownership over parent content.

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

## Standalone Rust / Cargo Boundary

The AgentCanon `rust/` tree owns standalone implementation, Cargo metadata,
fixtures, and producer tests. The live manifest therefore declares
`projection_forbidden_roots = ["rust"]`. Let `F` be every path equal to or below
`rust`, `T` the manifest-owned parent target paths, `S` the AgentCanon source
paths materialized by those entries, and `U` the update-transition candidates.
The required invariant is:

```text
prefix_intersection(T ∪ S ∪ U, F) = ∅
```

The parser also rejects an ancestor entry such as a broad root projection that
would contain `rust/`. Every renderer used by `sync_agent_canon.sh` loads and
validates the same manifest before producing link, copy, regular, cleanup, or
transition specifications, so no shell-local Rust allowlist exists. The
`projection-forbidden-roots` readback command exposes the policy without adding
it to the normalized runtime-surface snapshot.

A parent checker classifies observed paths by topology and ownership rather than
by a Rust-looking pathname alone:

| Observed path | Classification | Required handling |
| --- | --- | --- |
| `vendor/agent-canon/rust/**` inside the exact source checkout | AgentCanon standalone source/test | Validate only in the AgentCanon owner repository |
| parent-owned regular directory or file below `rust/**` | parent content or historical artifact | Do not infer projection and do not delete from AgentCanon sync |
| generated copy below `rust/**` | regular parent-owned bytes unless explicit parent provenance says otherwise | Remove or retain only through a parent issue/PR |
| symlink resolving into `vendor/agent-canon/rust/**` | unmanaged live projection edge | Fail the consumer structure check; never register it in the live manifest |
| gitlink / submodule below `rust/**` | explicit parent dependency edge, not a live AgentCanon view | Keep under a parent-owned dependency contract or reject as an unmanaged projection |
| absent path | desired live-projection fixed point | No cleanup pathspec or compatibility placeholder |

Regular bytes cannot be identified as an AgentCanon projection from their path
or content hash alone. In particular, a historical
`rust/agent-canon/tests/python_algorithm_contract_cli.rs` in a consumer remains
parent-owned even when its origin can be traced to an old AgentCanon-related
change. The producer manifest must not claim it as `removed_legacy`,
`standalone_only`, repository state, or an update transition.

### Parent migration readback

A parent repository that removes such a regular artifact does so on a separate
parent issue branch. Before editing, read back both filesystem and index
identity:

```bash
git ls-files -s -- rust/agent-canon
git status --short -- rust/agent-canon
test ! -L rust/agent-canon
git submodule status -- rust/agent-canon 2>/dev/null || true
git log --all --follow -- rust/agent-canon/tests/python_algorithm_contract_cli.rs
```

Mode `100644` or `100755` is a regular parent file, mode `120000` is a symlink,
and mode `160000` is a gitlink. A regular-file removal must be staged and
validated with the parent repository's own checks; `link-root` is not the
migration command. The parent PR records the old index mode/blob, deletion
diff, selected validation, and post-change absence.

The standalone Rust gate remains
`tools/ci/run_standalone_static_gate_unit.sh` in the AgentCanon source owner. A
live parent's standard projection check does not add Cargo setup or this Rust
gate merely because the pinned checkout contains `rust/`. GPU execution,
runtime-alignment, and other live-parent command packets consume the declared
root views and cannot broaden validation from source-tree presence alone.

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
python3 -m unittest -v \
  tests/agent_tools/test_codex_projection_boundary.py \
  tests/agent_tools/test_rust_projection_boundary.py
python3 tools/agent_tools/surface_manifest.py --root . --prefix . \
  projection-forbidden-roots
python3 tools/agent_tools/surface_manifest.py --root . --prefix . check-doc
bash tools/ci/run_standalone_static_gate_unit.sh rust
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
