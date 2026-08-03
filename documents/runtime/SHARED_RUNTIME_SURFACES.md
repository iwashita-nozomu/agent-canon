<!--
@dependency-start
contract reference
responsibility Documents Shared Runtime Surfaces for this repository.
upstream design ../contracts/github-first-module-and-devcontainer-policy.md canonical topic workspace and VS Code workspace boundary
downstream design ./shared-runtime-surfaces.toml machine-readable surface manifest
downstream design ../experiments/gpu-admission-r5-source-packet.md exact shared runtime identity contract
downstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
downstream implementation ../../tools/agent_tools/surface_manifest.py parses the surface manifest
downstream implementation ../../tools/sync_agent_canon.sh enforces root-view synchronization
downstream implementation ../../tools/agent_tools/check_convention_compliance.py verifies manifest/doc wiring
downstream design ../agent-canon/agent-canon-parent-repo-latest-checklist.md task-start parent repo checklist
@dependency-end
-->

# Shared Runtime Surfaces

This document defines how `vendor/agent-canon/` is exposed into a template or
derived repository root. The machine-readable source of truth is
`documents/runtime/shared-runtime-surfaces.toml`; this document explains the ownership
rules for readers and reviewers.

The template and its derived repositories may be tightly coupled to AgentCanon
because they are cloned from the template. That coupling is intentional. The
boundary that must stay clear is ownership: each root path must say who owns it,
whether a derived repository may override it, and where edits must be made.

Target-State-First, Decision Sufficiency, model/profile, ToolCall, capacity,
and lifecycle behavior remains an AgentCanon-owned generated projection. Root
views link to the canonical workflow, subagent, communication, registry,
handshake, and closeout owners; they are not independent policy sources.

## Reader Map

Use this document to answer who owns each shared runtime surface exposed from
`vendor/agent-canon/` into a template or derived repository root. Reusable
template sources remain under `vendor/agent-canon/templates/`; the parent root
does not expose a `templates` symlink view. Start with Owner Classes and
Manifest Contract, then read the symlink, active-contract, durable-state,
GitHub copy, documents, evidence, memory, notes, and tests sections for
path-specific ownership. Editing Rule and Validation close the workflow for
changes to shared surfaces.

Root `templates/` is not a shared-surface path after this migration. A
template or derived repository may own a regular `templates/` directory;
`link-root` and `check` leave that parent content unchanged. They also do
not remove the formerly tracked shared symlink; the parent integration confirms
its exact mode and target before running `git rm templates`.

## Owner Classes

| Owner class | Root behavior | Edit source | Local override |
| --- | --- | --- | --- |
| AgentCanon-owned runtime surface | individual symlink view into `vendor/agent-canon/` | independent AgentCanon source clone | no |
| AgentCanon-owned shared policy | standalone under `vendor/agent-canon/documents/` | AgentCanon source | no |
| Template-owned active contract | regular root file when the template or derived repo creates one | template or derived repo root | yes |
| Project-owned durable state / content | regular project-local file or directory | project root | yes |
| Update transaction state | regular task-owned records under `.agent-canon/update-lifecycle/state/` | AgentCanon update transaction | no |
| Update generated evidence | regular generated records under `.agent-canon/update-lifecycle/evidence/` | named lifecycle evidence producer | no |
| Update projection view | regular queue/frontier records under `.agent-canon/update-lifecycle/projection-queue/` | AgentCanon update transaction | no |
| GitHub path constraint copy surface | regular root copy from AgentCanon source | AgentCanon source, then `link-root` copy | no |
| AgentCanon standalone-only surface | absent from template root; `link-root` removes stale root views | standalone AgentCanon repo | no |

## Manifest Contract

`documents/runtime/shared-runtime-surfaces.toml` lists every synchronized surface with
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

### sync_control と full-sync trigger の責務

`shared-runtime-surfaces.toml` の `sync_control=true` は、共有 Runtime を
更新する `tools/sync_agent_canon.sh` の対象領域（`sync` 系スクリプトや checker の
実行結果を含む）を明示します。これは次の3条件を満たすときのみ
`full sync` 系の判定が成立することを意味します。

1. リフレッシュ対象の materialized copy / root link topology / sync 実装・manifest
   自体のパスが変更されたとき。
2. 変更したパスの実体が同一であることが、`check` コマンドで再現可能であること。
3. ノード（対象パス）ごとに remote / pin / manifest の参照整合が
   `toolchain` の受け口（`tool` 層）で確認できること。

`check_agent_canon_latest` はこの所有者契約に従って、
`update` action と link-root の main 追従を結果として扱います。
pin の可到達性と `gitlink == submodule worktree HEAD` は read-only 必須条件であり、
`fail` を返す唯一の理由です。`dirty`（未追跡含む）自体は
`AGENT_CANON_LATEST_SUBMODULE_WORKTREE_CLEAN=no` になりますが、read-only では
`pass` 扱いを維持し、`AGENT_CANON_LATEST_NEXT_ACTION` で更新時の保全方針を示します。
`deferred` は本契約上は「mainとの差分の更新待ち」だけで、到達不能や不一致を
更新未実施のまま通過させる経路には使いません。materialization 上書き更新を行う
場合のみブロックとし、通常 CI/PR の判定からは切り離して扱います。

## AgentCanon-Owned Symlink Views

AgentCanon-owned runtime and policy paths are symlink views in the template root.
For a dependency source change, read
`documents/rule/dependency-module-changes.md` first and edit the independent
topic-workspace managed source clone. The `vendor/agent-canon/` path is only a
clean pin/runtime projection. Repair the root view with:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  bash tools/sync_agent_canon.sh link-root
```

Core runtime surfaces include `AGENTS.md`, `agents/`, `.agents/`,
`.codex/config.toml`, `.codex/README.md`, `.codex/agents/`,
`.codex/hooks.json`, `.codex/hooks/`, `.devcontainer/`, and `tools/`.
Reusable AgentCanon templates are not part of this root-link set. Parent
consumers resolve them through `vendor/agent-canon/templates/`, while the
standalone AgentCanon source resolves them from its source-root
`templates/` directory.
`.vscode/` is a parent-owned regular container whose
`c_cpp_properties.json`, `extensions.json`, `settings.json`, and `tasks.json`
children are the four individual AgentCanon symlink surfaces. Work-area
composition follows the canonical filesystem/lifecycle and VS Code workspace
boundary in [`contracts/github-first-module-and-devcontainer-policy.md`](../contracts/github-first-module-and-devcontainer-policy.md):
use `PARENT_ROOT`, `SOURCE_CLONE`, and `CONTINUE_PATH` within the Git-ignored
`workspace/<topic-slug>/` clone lifecycle. This document owns the shared `.vscode/`
surface, not dependency clone composition.
These paths are installed capability. The active profile and required checks
are selected by `documents/runtime/runtime-profiles-and-check-matrix.md`.

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

The standalone AgentCanon source owns the real `tools/` directory. In a template
or derived parent repository, Root `tools/` is a parent-owned regular container,
and its shared-canon child is the single symlink
`tools/agent-canon -> ../vendor/agent-canon/tools`.

Parent repositories call shared tooling through the explicit AgentCanon
namespace, such as
`python3 tools/agent-canon/agent_tools/check_convention_compliance.py`.
Parent-local automation may live directly under root `tools/`, while shared
tool edits use the independent source-clone route in
`documents/rule/dependency-module-changes.md`. The container and child symlink
prevent parent-local tools from being mixed into the AgentCanon source.
Project-local automation must stay in project-owned paths, and the pinned
implementation source remains `vendor/agent-canon/tools/`.

Inventory and review tooling must distinguish these roles: standalone
`tools/` is the AgentCanon source, parent `tools/` is a local container, and
`tools/agent-canon` is the only shared-tool projection in that container.
### Parent Copy Projection

The AgentCanon source keeps `.github/` copy surfaces executable in the
standalone source layout. When `sync_agent_canon.sh` runs through a vendored
submodule, it deterministically projects those copies to the parent layout:
root shared-tool paths use `tools/agent-canon/`, and AgentCanon-only relative
paths use `vendor/agent-canon/documents/` or `vendor/agent-canon/issues/`.
`link-root` writes this projection and `check` compares against the same
projection. Parent repositories must not hand-edit the generated copies or
add compatibility links under the root `tools/` container.

GitHub-facing AgentCanon symlink views include `.github/AGENTS.md`.

Shared policy documents are not exposed as root `documents/` symlink views in
template or derived repositories. They remain available under
`vendor/agent-canon/documents/`, including review, workflow, coding conventions,
OOP guidance, experiment policy, dependency manifest policy, worktree lifecycle,
conventions subtrees, tool docs, reusable templates, `documents/README.md`,
`documents/contracts/template-bootstrap.md`, and
`documents/contracts/github-first-module-and-devcontainer-policy.md`. Parent repositories
decide which repo-specific documents appear in root `documents/`.

`.devcontainer/` is a parent-owned runtime container directory in derived repos.
Its minimum shared shape is the symlink
`.devcontainer/devcontainer.json -> ../vendor/agent-canon/.devcontainer/devcontainer.json`
and any parent-specific source such as `post-create-parent.sh`. The linked config
calls shared scripts directly under `vendor/agent-canon/.devcontainer/`; parent
wrappers and copied shared scripts are not part of the surface. Generated Compose
is written to the ignored parent state path `.agent-canon/docker-compose.generated.yml`.

The devcontainer consumes repo-local `docker/Dockerfile`,
`docker/packs/default.toml`, and `docker/install_python_dependencies.sh`; it does
not make `docker/` AgentCanon-owned.

GPU admission runtime identity scripts (`bootstrap-shared-runtime.sh`,
`finalize-shared-runtime.sh`, `post-attach.sh`) remain in AgentCanon source and are
invoked from the linked config by their direct `vendor/agent-canon/.devcontainer/`
paths. The exact
receipt paths and parser/writer ownership are defined by
`documents/experiments/gpu-admission-r5-source-packet.md` and
`agent-canon-environment.toml`.

`parent-hook` must not replace AgentCanon shared stages. The linked config runs
`vendor/agent-canon/.devcontainer/post-create.sh` first, then
`.devcontainer/post-create-parent.sh` in `set -e` mode. If AgentCanon standard
`post-create` fails, the parent hook is not executed.

`.vscode/` is also a shared AgentCanon runtime ergonomics surface. The parent
owns the real directory container; AgentCanon owns the individual
`c_cpp_properties.json`, `extensions.json`, `settings.json`, and `tasks.json`
symlink surfaces. The dependency source work area follows the canonical
filesystem/lifecycle and VS Code workspace boundary and uses the paths returned
by `dependency_module_change.py prepare`; it is not a shared surface source.
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
- `documents/contracts/template-bootstrap.md`
- `documents/contracts/template-github-remote.md`
- `documents/contracts/linux-wsl-host-requirements.md`
- `documents/contracts/server-host-contract.md`
- `documents/contracts/remote-execution-repo-contract.md`
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

AgentCanon may provide generic templates under the standalone source path
`templates/documents/`, such as `server_host_inventory.template.md`,
`server_runtime_layout.template.toml`,
`remote_execution_repo.template.toml`, and
`remote_execution_target.template.toml`. A parent resolves the same inputs
under `vendor/agent-canon/templates/documents/`; they are not the derived
repo's active contract.

## Project-Owned Durable State And Content

Project state remains regular root content. AgentCanon must not restore these as
shared symlinks or shared copies:

- `goal.md`
- `.agent-canon/update-lifecycle/state/`
- `.agent-canon/update-lifecycle/evidence/`
- `.agent-canon/update-lifecycle/projection-queue/`
- `experiments/README.md`
- `experiments/registry.toml`
- `experiments/<topic>/`
- `reports/`
- project-specific design documents
- project-specific implementation notes

`goal.md` is always repo-local state. If a legacy root has `goal.md` symlinked
to AgentCanon, `link-root` converts it to a repo-local placeholder.

The three update-lifecycle children are one owner namespace with distinct
roles: resumable state, generated evidence, and a projection-only queue view.
The update transaction may clean its own records after remote readback; it must
leave every unknown sibling under `.agent-canon/` unchanged.

## GitHub Path Constraint Copies

GitHub requires some files to exist at root paths where symlinks are not the
right operational surface. These paths remain regular root files but are copied
from AgentCanon:

- `.github/workflows/agent-coordination.yml`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
- `.github/scripts/checkout_agent_canon_submodule.sh`

Do not edit these root copies as independent truth surfaces. Edit the
AgentCanon source, then run the request-evidence-authorized
`bash tools/sync_agent_canon.sh link-root` command.
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

`documents/agent-canon/agent-canon-update-route.md` is the standalone source entry for the
update transaction. A parent consumes it under `vendor/agent-canon/documents/`;
it does not copy that contract into root `documents/` or treat projection queue
records as source canon.

## Evidence Contract Boundary

`evidence/` is an AgentCanon shared runtime evidence contract. Root template
and derived repositories use it as a symlink view into
`vendor/agent-canon/evidence/` so CI eval producers can resolve the same
deterministic manifests from either standalone AgentCanon or a submodule parent
checkout. Generated eval output does not live in this root view; it stays in the
mounted runtime log archive described by `documents/runtime/runtime-log-archive.md`.

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

- Read `documents/rule/dependency-module-changes.md` before any dependency
  source edit. Edit generic AgentCanon source in the exact topic clone
  `workspace/<topic-slug>/<module-basename>`; never use a vendored checkout as a
  source branch.
- Edit template-owned active contracts at the root after they are regular
  files.
- Edit project-owned durable state at the root.
- Repair root symlinks and GitHub copy surfaces with the request-evidence-authorized
  `bash tools/sync_agent_canon.sh link-root` command.
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
