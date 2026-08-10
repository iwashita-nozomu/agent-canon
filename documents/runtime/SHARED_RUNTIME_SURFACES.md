<!--
@dependency-start
contract reference
responsibility Documents Shared Runtime Surfaces for this repository.
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace boundary
downstream design ./shared-runtime-surfaces.toml machine-readable surface manifest
downstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
downstream implementation ../../tools/agent_tools/surface_manifest.py parses the surface manifest
downstream implementation ../../tools/sync_agent_canon.sh enforces root-view synchronization
downstream implementation ../../tools/agent_tools/check_convention_compliance.py verifies manifest/doc wiring
@dependency-end
-->

# Shared Runtime Surfaces

This document defines the small set of AgentCanon views exposed from
`vendor/agent-canon/` into a template or derived repository. The machine-readable
source of truth is `documents/runtime/shared-runtime-surfaces.toml`. General
path ownership and path classes are declared only by
`responsibility-scope.toml`; this manifest describes projection mechanics.

AgentCanon source is authoritative under `vendor/agent-canon/`. The root
projection contains only the instruction view `AGENTS.md`, the runtime config
view `.codex/config.toml`, and the shared CLI/tool namespace
`tools/agent-canon`. The update lifecycle may create optional transaction state
under `.agent-canon/`. Tests, notes, memory, evidence, editor, and GitHub paths
are not mirrored shared surfaces. Parent `.devcontainer/` content is likewise
never projected: `devcontainer.json`, `rootless/`, and `gpu-admission/` are
retired/non-projecting paths. A parent may own regular files at those paths;
only a stale symlink that still resolves into AgentCanon is eligible for removal
during migration.
Standalone AgentCanon may retain and validate its own regular `.vscode` source
files; that standalone source ownership is separate from any parent `.vscode`
directory, which remains parent-owned regular content.
Standalone AgentCanon's `.devcontainer/` is likewise source-owned environment
content and is not projected into a parent root. Its default selector asks the
generator to inspect Docker's official `SecurityOptions` and auto-resolves
rootful `project` or rootless `0:0` identity. Optional host credentials and zsh
mounts target the resolved runtime `HOME` only when explicitly selected.

## Reader Map

Read Projection Metadata and Manifest Contract to understand synchronization,
then use Projection, Editing Rule, and Validation for an operation. Parent repositories
may create regular project-owned files or directories at any path that is not
listed as an AgentCanon projection; synchronization preserves that content.

## Projection Metadata

| Projection kind | Root behavior | Edit source | Local override |
| --- | --- | --- | --- |
| AgentCanon runtime surface | symlink view into `vendor/agent-canon/` | independent AgentCanon source clone | no |
| AgentCanon source | submodule or standalone source checkout | AgentCanon source | no |
| Project-owned content | regular file or directory in the parent repository | parent repository | yes |
| Update transaction state | optional records under `.agent-canon/` | selected update transaction | no |
| Retired root view | absent; stale symlinks are removed by `link-root` | none | parent regular content is preserved |

## Manifest Contract

Each `[[surface]]` in `shared-runtime-surfaces.toml` declares projection metadata:

- `path`: root-relative path of the view;
- `mode`: `symlink` or `repo_state` for active surfaces;
- `projection_producer`: the process or source family that produces the view;
- `projection_kind`: synchronization behavior metadata;
- `source`: optional AgentCanon-relative source path; and
- `optional`: whether the path is materialized only by an explicit lifecycle.

The `removed_legacy` group records paths that must not be materialized. The
manifest contains no general path-owner fallback and no full-tree or
all-tracked entry. `projection_producer` and `projection_kind` describe only
root synchronization mechanics; they are not path ownership or responsibility
classes. `responsibility-scope.toml` is the sole general owner/class source.
`surface_manifest.py` checks this document against the manifest before the
synchronization command is used.

## Projection

The active projection is deliberately limited to:

| Root path | Mode | Source |
| --- | --- | --- |
| `AGENTS.md` | symlink | `ROOT_AGENTS.md` |
| `.codex/config.toml` | symlink | `.codex/config.toml` |
| `tools/agent-canon` | symlink | `tools` |
| `.agent-canon` | optional transaction state | update lifecycle |

The standalone source may keep its own `rootless/` and `gpu-admission/`
selectors. Those source files are not parent projections and are validated only
when AgentCanon is checked as a standalone source root.

Root `tools/` is a parent-owned regular container; only its `agent-canon` child
is shared. The standalone source owns `vendor/agent-canon/tools/`, and the
parent view is `tools/agent-canon -> ../vendor/agent-canon/tools`. AgentCanon
templates and documents remain available under `vendor/agent-canon/` and are
not copied into parent root views. A regular
parent file or directory at a retired path is left untouched; only a stale
AgentCanon symlink is eligible for removal.

## Editing Rule

Edit generic AgentCanon behavior in the managed topic clone described by
`documents/rule/dependency-module-changes.md`; do not edit a vendored pin as a
source branch. Edit parent-specific contracts and project content in the parent
repository. Repair root views through the source-root resolver:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
    exec tools/sync_agent_canon.sh link-root
```

`link-root` and `check` consume the manifest and do not maintain a second
hard-coded list. They must preserve parent-owned regular content and may remove
only stale symlinks for entries in the retired group. A missing path is created
only after checking the manifest, source tree, and owner map.

Project-local automation must stay in project-owned paths; the shared namespace
does not absorb parent tools.

## Validation

Run the checks selected by the active runtime profile and touched surface:

```bash
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/agent_tools/surface_manifest.py check-doc
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/agent_tools/check_convention_compliance.py
```

The completion evidence is the manifest readback, the root-view `check` result,
and the selected profile checks. No universal test, memory, evidence, editor,
devcontainer, or GitHub projection check is implied by this document.
