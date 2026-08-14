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

This document owns the named **`live-agent-canon` explicit opt-in integration**. It is not the
normal template/bootstrap contract. The default consumer uses the static seed defined by
`documents/contracts/static-seed-export.md`, owns those files directly, and does not consult this
manifest, discover an AgentCanon source root, project runtime views, or maintain update state.

A repository selects this document only through a separately reviewed architecture decision that
requires live AgentCanon behavior. Merely cloning a template, initializing a project, running CI,
or building a product image is not selection evidence.

## Selection Boundary

| Mode | Default | Source requirement | Root behavior |
| --- | --- | --- | --- |
| Static seed consumer | yes | none after maintainer export | consumer-owned regular files; no projection or update state |
| `live-agent-canon` integration | no | explicit AgentCanon source checkout | manifest-owned symlink views and optional transaction state |

The machine-readable source of truth for the opt-in mode is
`documents/runtime/shared-runtime-surfaces.toml`. It records
`integration_mode = "live-agent-canon"`, `default_consumer = false`, and
`selection = "explicit-opt-in"`. A default-consumer checker must reject those live surfaces rather
than silently selecting this manifest.

## Opt-in Source and Projection

AgentCanon source is authoritative under `vendor/agent-canon/` only after the opt-in mode is
selected. The root projection then contains only the instruction view `AGENTS.md`, the Codex
runtime config bundle `.codex/config.toml` and `.codex/agents`, and the shared CLI/tool namespace
`tools/agent-canon`. The update lifecycle may create optional transaction state under
`.agent-canon/`.

Tests, notes, memory, evidence, editor, GitHub, and parent `.devcontainer/` paths are not mirrored
shared surfaces. Parent-owned regular content at retired paths is preserved; only a stale symlink
that still resolves into the selected AgentCanon source is eligible for removal during migration.
Standalone AgentCanon may retain source-owned `.vscode` and `.devcontainer` content. That standalone
ownership does not select live integration for a parent repository.

## Reader Map

Use this document only after explicit selection. Read Projection Metadata and Manifest Contract to
understand synchronization, then use Projection, Editing Rule, and Validation. For normal template
creation or repository bootstrap, return to `documents/contracts/template-bootstrap.md` instead.

## Projection Metadata

| Projection kind | Root behavior | Edit source | Local override |
| --- | --- | --- | --- |
| AgentCanon runtime surface | symlink view into `vendor/agent-canon/` | independent AgentCanon source clone | no |
| AgentCanon source | explicitly selected source checkout | AgentCanon source | no |
| Project-owned content | regular file or directory in the parent repository | parent repository | yes |
| Update transaction state | optional records under `.agent-canon/` | selected update transaction | no |
| Retired root view | absent; stale AgentCanon symlinks may be removed | none | parent regular content is preserved |

## Manifest Contract

Each `[[surface]]` in `shared-runtime-surfaces.toml` declares projection metadata:

- `path`: root-relative path of the view;
- `mode`: `symlink` or `repo_state` for active surfaces;
- `projection_producer`: the process or source family that produces the view;
- `projection_kind`: synchronization behavior metadata;
- `source`: optional AgentCanon-relative source path; and
- `optional`: whether the path is materialized only by an explicit lifecycle.

The top-level integration metadata is mandatory selection evidence for readers and focused tests.
The `removed_legacy` group records paths that must not be materialized. The manifest contains no
general path-owner fallback and no full-tree or all-tracked entry. `responsibility-scope.toml` remains
the sole general owner/class source.

## Projection

The active projection for the explicitly selected live mode is deliberately limited to:

| Root path | Mode | Source |
| --- | --- | --- |
| `AGENTS.md` | symlink | `ROOT_AGENTS.md` |
| `.codex/config.toml` | symlink | `.codex/config.toml` |
| `.codex/agents` | symlink | `.codex/agents` |
| `tools/agent-canon` | symlink | `tools` |
| `.agent-canon` | optional transaction state | update lifecycle |

Root `tools/` is a parent-owned regular container; only its `agent-canon` child is shared in the
opt-in mode. The standalone source owns `vendor/agent-canon/tools/`, and the parent view is
`tools/agent-canon -> ../vendor/agent-canon/tools`. AgentCanon templates and documents remain in the
source checkout and are not copied into parent root views. A regular parent file or directory at a
retired path is left untouched.

## Editing Rule

Edit generic AgentCanon behavior in the managed topic clone described by
`documents/rule/dependency-module-changes.md`; do not edit a vendored pin as a source branch. Edit
parent-specific contracts and project content in the parent repository. Only a repository that has
selected the live mode may repair root views through the source-root resolver:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
    exec tools/sync_agent_canon.sh link-root
```

`link-root` and `check` consume the manifest and do not maintain a second hard-coded list. They must
preserve parent-owned regular content and may remove only stale symlinks for entries in the retired
group. A missing path is created only after checking the manifest, source tree, and owner map.

Project-local automation must stay in project-owned paths; the shared namespace does not absorb
parent tools.

## Validation

Run these checks only for the explicitly selected live integration:

```bash
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/agent_tools/surface_manifest.py check-doc
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/agent_tools/check_convention_compliance.py
```

Default static consumers instead use the source-hidden consumer and bootstrap validation from the
static seed contract. No live projection check is implied by a normal clone, bootstrap, test, docs,
Docker, or CI operation.
