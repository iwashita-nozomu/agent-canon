<!--
@dependency-start
contract reference
responsibility Documents Shared Runtime Surfaces for this repository.
downstream design ./shared-runtime-surfaces.toml machine-readable surface manifest
downstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
downstream implementation ../tools/agent_tools/surface_manifest.py parses the surface manifest
downstream implementation ../tools/sync_agent_canon.sh enforces root-view synchronization
downstream implementation ../tools/agent_tools/check_convention_compliance.py verifies manifest/doc wiring
downstream design ./agent-canon-parent-repo-latest-checklist.md task-start parent repo checklist
@dependency-end
-->

# Shared Runtime Surfaces

This document defines how `vendor/agent-canon/` is exposed into a template or
derived repository root. The machine-readable source of truth is
`documents/shared-runtime-surfaces.toml`; this document explains the ownership
rules for readers and reviewers.

The template and its derived repositories may be tightly coupled to AgentCanon
because they are cloned from the template. That coupling is intentional. The
boundary that must stay clear is ownership: each root path must say who owns it,
whether a derived repository may override it, and where edits must be made.

## Reader Map

Use this document to answer who owns each shared runtime surface exposed from
`vendor/agent-canon/` into a template or derived repository root. Start with
Owner Classes and Manifest Contract, then read the symlink, active-contract,
durable-state, GitHub copy, documents, evidence, memory, notes, and tests
sections for path-specific ownership. Editing Rule and Validation close the
workflow for changes to shared surfaces.

## Owner Classes

| Owner class | Root behavior | Edit source | Local override |
| --- | --- | --- | --- |
| AgentCanon-owned runtime surface | symlink view into `vendor/agent-canon/` | AgentCanon source | no |
| AgentCanon-owned shared policy | standalone under `vendor/agent-canon/documents/` | AgentCanon source | no |
| Template-owned active contract | regular root file when the template or derived repo creates one | template or derived repo root | yes |
| Project-owned durable state / content | regular project-local file or directory | project root | yes |
| GitHub path constraint copy surface | regular root copy from AgentCanon source | AgentCanon source, then `link-root` copy | no |
| AgentCanon standalone-only surface | absent from template root; `link-root` removes stale root views | standalone AgentCanon repo | no |

## Manifest Contract

`documents/shared-runtime-surfaces.toml` lists every synchronized surface with
these fields:

- `path`: root-relative path in the template or derived repo.
- `mode`: `symlink`, `copy`, `regular`, `repo_state`, `standalone_only`, or
  `removed_legacy`.
- `owner`: the owner class in machine-readable form.
- `class`: the behavior class, such as `runtime_surface`, `shared_policy`,
  `active_contract`, `durable_state`, `test_mirror`, or `github_copy`.
- `source`: optional AgentCanon-relative source when it differs from `path`.
- `local_override_allowed`: whether a derived repo may make the root path its
  own truth surface after clone.

`tools/sync_agent_canon.sh` reads the manifest through
`tools/agent_tools/surface_manifest.py`. The shell script must not carry a
separate long hard-coded list of root paths. If the manifest and this document
disagree, update the manifest first and then adjust this reader-facing policy.

## AgentCanon-Owned Symlink Views

AgentCanon-owned runtime and policy paths are symlink views in the template root.
Edit the `vendor/agent-canon/` source, then repair the root view with:

```bash
bash tools/sync_agent_canon.sh link-root
```

Core runtime surfaces include `AGENTS.md`, `agents/`, `.agents/`,
`.codex/config.toml`, `.codex/README.md`, `.codex/agents/`,
`.codex/hooks.json`, `.codex/hooks/`, `.devcontainer/`, `.vscode/`, and
`tools/`.
These paths are installed capability. The active profile and required checks
are selected by `documents/runtime-profiles-and-check-matrix.md`.

### Project-Owned Skill Lane

Parent repositories may add repo-specific Codex skills under
`.codex/project-skills/<skill-id>/SKILL.md`. This lane is project-owned regular
content and must not be symlinked into `vendor/agent-canon/.agents` or mixed
into the AgentCanon `.agents/skills/` public catalog. If a parent root needs a
repo-specific skill, it uses the optional parent-owned overlay
`.codex/project-config.toml` with `[[skills.config]] path =
"project-skills/<skill-id>/SKILL.md"`. Parent repositories must not edit the
AgentCanon-owned symlink view `.codex/config.toml` to enable project-local
skills.

AgentCanon-owned `.agents/skills/` remains the shared public skill surface.
`check_agent_runtime_alignment.py` validates both config lanes: all AgentCanon
public shims must stay enabled from `.codex/config.toml`, and any extra
configured skill must come from `.codex/project-config.toml` and live under the
project-owned `.codex/project-skills/` lane. `link-root` does not populate
either parent-owned path; both are optional project content.

### Tools Directory Boundary

Root `tools/` is a symlink view, not a project-local implementation directory.
Its source is `vendor/agent-canon/tools/`, which owns shared agent tooling,
workflow automation, CI helpers, container runners, document maintenance tools,
and static-analysis utilities.

Parent repositories call shared tooling through the stable root command path,
such as `python3 tools/agent_tools/check_convention_compliance.py`, while edits
to those tools are made in `vendor/agent-canon/tools/...` and routed through
AgentCanon. Project-local automation must stay in project-owned paths, such as
`scripts/`, package-local modules, project-specific CI files, or another
repo-owned path. A derived repository must not turn root `tools/` into a mixed
directory or add project-specific files under that symlink view.

Inventory and review tooling should distinguish these roles: `tools/` at the
root is the AgentCanon tool view, and `vendor/agent-canon/tools/` is the
AgentCanon tool source.

GitHub-facing AgentCanon symlink views include `.github/AGENTS.md`.

Shared policy documents are not exposed as root `documents/` symlink views in
template or derived repositories. They remain available under
`vendor/agent-canon/documents/`, including review, workflow, coding conventions,
OOP guidance, experiment policy, dependency manifest policy, worktree lifecycle,
conventions subtrees, tool docs, reusable templates, `documents/README.md`,
`documents/template-bootstrap.md`, and
`documents/github-first-module-and-devcontainer-policy.md`. Parent repositories
decide which repo-specific documents appear in root `documents/`.

`.devcontainer/` is a shared AgentCanon runtime ergonomics surface. It may
generate `.devcontainer/docker-compose.generated.yml` locally, but the source
scripts, `devcontainer.json`, post-create setup, and attach status reporting are
edited in AgentCanon. The devcontainer consumes repo-local `docker/Dockerfile`,
`docker/packs/default.toml`, and `docker/install_python_dependencies.sh`; it
does not make `docker/` AgentCanon-owned.

`.vscode/` is also a shared AgentCanon runtime ergonomics surface. It owns
workspace settings, recommended extensions, and VS Code task entrypoints that
should behave the same in AgentCanon, template, and derived repository roots.
Do not store personal editor state, host-specific include paths, workspace-local
secrets, or product-specific commands in the shared `.vscode/` view. Put
project-specific editor guidance in repo-local docs or project-owned scripts
instead.

## Template-Owned Active Contracts

These root files may describe the current template or derived repository. They
are regular files, not symlink views, only when the parent repository creates
and owns them:

- `README.md`
- `QUICK_START.md`
- `documents/README.md`
- `documents/template-bootstrap.md`
- `documents/template-github-remote.md`
- `documents/linux-wsl-host-requirements.md`
- `documents/server-host-contract.md`
- `documents/remote-execution-repo-contract.md`
- `docker/README.md`
- `scripts/README.md`
- `notes/README.md`
- `.gitmodules`

`link-root` no longer materializes AgentCanon documents into root `documents/`.
A derived repo may create its own server contract, bootstrap contract, host
requirements, template remote policy, or root `documents/README.md`; those files
are reviewed and committed as template or derived-repo content.

`standalone_only` manifest entries are intentionally absent from template and
derived repo roots. If a legacy symlink or copy remains at such a path,
`bash tools/sync_agent_canon.sh check` reports it and `link-root` removes it.

AgentCanon may provide generic templates under `documents/templates/`, such as
`server_host_inventory.template.md`, `server_runtime_layout.template.toml`,
`remote_execution_repo.template.toml`, and
`remote_execution_target.template.toml`. Those are shared policy/template
inputs; they are not the derived repo's active contract.

## Project-Owned Durable State And Content

Project state remains regular root content. AgentCanon must not restore these as
shared symlinks or shared copies:

- `goal.md`
- `.agent-canon/update-state.toml`
- `experiments/README.md`
- `experiments/registry.toml`
- `experiments/<topic>/`
- `reports/`
- project-specific design documents
- project-specific implementation notes

`goal.md` is always repo-local state. If a legacy root has `goal.md` symlinked
to AgentCanon, `link-root` converts it to a repo-local placeholder.

## GitHub Path Constraint Copies

GitHub requires some files to exist at root paths where symlinks are not the
right operational surface. These paths remain regular root files but are copied
from AgentCanon:

- `.github/workflows/agent-coordination.yml`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
- `.github/scripts/checkout_agent_canon_submodule.sh`

Do not edit these root copies as independent truth surfaces. Edit the
AgentCanon source, then run `bash tools/sync_agent_canon.sh link-root`.
The `.github/scripts/checkout_agent_canon_submodule.sh` root copy is only a
GitHub-path wrapper; the shared checkout implementation lives in
`tools/ci/checkout_agent_canon_submodule.sh`.

## Documents Directory Ownership

Root `documents/` is parent-repo owned. It should contain repo-specific
architecture, design, contracts, and implementation-specific specs. Shared
AgentCanon documents stay under `vendor/agent-canon/documents/`; root docs may
link there when readers need shared conventions or workflow policy. Generated or
experiment artifacts stay under `reports/` or `experiments/` unless they become
a durable repo-local design or policy surface.

## Evidence Contract Boundary

`evidence/` is an AgentCanon shared runtime evidence contract. Root template
and derived repositories use it as a symlink view into
`vendor/agent-canon/evidence/` so CI eval producers can resolve the same
deterministic manifests from either standalone AgentCanon or a submodule parent
checkout. Generated eval output does not live in this root view; it stays in the
mounted runtime log archive described by `documents/runtime-log-archive.md`.

## Memory And Notes Boundary

`memory/USER_PREFERENCES.md` and `memory/AGENT_PHILOSOPHY.md` are AgentCanon
shared runtime memory. They are global user-agent and agent-operating notes, not
project-specific design logs.

`notes/README.md` is repo-local. Under `notes/`, shared templates and global
guardrails may be AgentCanon symlinks, while project-specific knowledge,
themes, failures, branch notes, worktree logs, and experiment notes belong to
the template or derived repo. If a preference should apply across repositories,
promote it through the AgentCanon memory workflow instead of burying it in a
project-local note.

## Tests Directory Ownership

`tests/` is also mixed:

- `tests/agent_tools/`: AgentCanon-owned symlink mirror for shared runtime
  tooling tests.
- `tests/tools/`: AgentCanon-owned symlink mirror for shared tool and workflow
  tests.
- `tests/project/` or package-specific test directories: project-local
  implementation tests owned by the derived repo.

Failures in root `tests/agent_tools/` or `tests/tools/` usually indicate
AgentCanon tooling or root-view drift; their canonical source files live under
`vendor/agent-canon/tests/agent_tools/` and `vendor/agent-canon/tests/tools/`.
Failures in project-local test namespaces usually belong to the derived repo
implementation.

## Editing Rule

- Edit AgentCanon-owned symlink views in `vendor/agent-canon/`.
- Edit template-owned active contracts at the root after they are regular
  files.
- Edit project-owned durable state at the root.
- Repair root symlinks and GitHub copy surfaces with
  `bash tools/sync_agent_canon.sh link-root`.
- Audit root-view drift with `bash tools/sync_agent_canon.sh check`.
- Before recreating a missing shared path, check the template root,
  `vendor/agent-canon/`, standalone AgentCanon, the manifest, and
  `tools/sync_agent_canon.sh`.

## Validation

```bash
python3 tools/agent_tools/surface_manifest.py check-doc
bash tools/sync_agent_canon.sh check
python3 tools/agent_tools/check_convention_compliance.py
make agent-checks
make agent-canon-pr-check
```
