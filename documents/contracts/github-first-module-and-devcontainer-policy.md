<!--
@dependency-start
contract policy
responsibility Documents GitHub-first reusable module and devcontainer ownership policy.
downstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership
downstream design ../rule/dependency-module-changes.md general dependency source-clone rule
downstream design ../conventions/coding-conventions-project.md project environment rules
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream environment ../../.devcontainer/devcontainer.json shared devcontainer entrypoint
downstream implementation ../../tools/ci/container_config.py validates Dockerfile and devcontainer boundaries
@dependency-end
-->

# GitHub-First Modules And Devcontainer Boundary

AgentCanon-owned reusable modules, skills, tools, and runtime surfaces assume a
GitHub source-of-truth path.

Source-edit and parent-projection responsibilities are defined by
[`rule/dependency-module-changes.md`](../rule/dependency-module-changes.md). This
document supplies the GitHub publication example; it does not authorize editing
`vendor/agent-canon` as a source branch.

The normal route is:

1. Confirm owner evidence and change AgentCanon in the topic workspace branch source clone.
1. Open an AgentCanon GitHub PR.
1. Merge to AgentCanon `main` after review and checks.
1. Update template or derived repos by advancing the `vendor/agent-canon`
   submodule pin.
1. Repair root views with the request-evidence-authorized
   source-root resolver `link-root` route.

Local Git remotes must not define the normal distribution path for
self-authored reusable modules.

## Reader Map

Use this policy to answer why reusable AgentCanon modules and devcontainer
surfaces use GitHub as the source-of-truth path. Read the opening route first,
then Local Git Boundary, Dockerfile Boundary, Devcontainer Boundary, VS Code
Surface Boundary, and Validation in order when changing shared runtime or
environment surfaces. Host-only local remotes are treated as repo-specific
problems, not shared architecture.

## Local Git Boundary

Repo-specific local Git problems are deferred to the repo that owns them.
AgentCanon shared architecture must not be shaped around a host-only path or a
one-machine remote name.

Required boundaries:

- record the GitHub SHA as the canonical evidence;
- keep local remote names out of shared Dockerfiles and shared default config;
- do not block shared-canon design on one repo's local Git repair.

## Dockerfile Boundary

`CONTAINER_OPERATIONS.md` is the canonical rulebook for this boundary. This
section is a GitHub-first architecture summary, not a second source of truth.

`docker/Dockerfile` is owned by the template or derived repo. It defines the
project runtime and build image.

Dockerfile content is limited to:

- OS packages needed by the project runtime, build, tests, or CI;
- project language runtimes and build libraries;
- safe-directory registration helpers needed before workspace mount;
- image-level smoke checks for runtime tools that belong to the project image.

Dockerfile content must not include agent-side convenience tooling:

- Codex CLI installation;
- npm / Node installation solely for Codex or agent tooling;
- GitHub CLI repository setup;
- `gh` installation or authentication setup;
- Rust toolchain installation for AgentCanon CLI or shared analysis tools;
- TeX / LaTeX installation solely for Academic Writing agent documents or
  diagrams;
- host auth material;
- host workspace or machine-local mount policy.

If a project genuinely needs Node, npm, or GitHub CLI as part of its own product
runtime, that project must document the product requirement in its repo-local
Docker docs and validation. Agent convenience is not enough.

## Devcontainer Boundary

`.devcontainer/` is AgentCanon-owned runtime ergonomics. Template and derived
repos expose it as a root symlink view into `vendor/agent-canon/.devcontainer`.

The shared devcontainer owns:

- declarative `.devcontainer/dependencies.toml` records for Codex, npm/Node
  when needed for Codex, and GitHub CLI / `gh`;
- declarative records for agent-side JSON inspection helpers such as `jq`;
- exact Rust toolchain and locked cargo source-build records for rustfmt,
  clippy, rust-analyzer, and the AgentCanon CLI when the source tree contains
  `rust/agent-canon/Cargo.toml`;
- declarative release/package records for shared TeX / LaTeX document and image
  tooling when the Academic Writing environment requires them;
- repository-specific devcontainer and Docker Compose project names, so template
  clones do not all create the same visible container names;
- host auth mount conventions for Codex, GitHub CLI, and SSH;
- optional private host-directory mounts through `AGENT_CANON_SECRET_DIR`, for
  confidential local Git remotes or other operator-local material that must not
  become a repository default;
- Docker socket mount detection and reporting;
- workspace attach status reporting;
- agent bootstrap ergonomics that should stay consistent across template
  clones.

The shared devcontainer consumes repo-local Docker runtime contracts instead of
owning them. It reads `docker/packs/default.toml`, builds the repo-local
`docker/Dockerfile`, forwards the pack runtime environment into the generated
Compose service, and runs repo-local `docker/install_python_dependencies.sh`
after the workspace is mounted.

When AgentCanon itself is opened as a standalone source checkout and no
`docker/packs/default.toml` exists, the generator builds the source-owned
`.devcontainer/Dockerfile` with the same canonical project UID/GID contract; it
does not fall back to an unpinned `ubuntu:22.04` image.

The default parent image contract is the #524 canonical identity: a
digest-pinned plain `ubuntu:22.04` base whose image creates the `project`
user/group from `PROJECT_UID` / `PROJECT_GID` build args and runs as
`USER project`. The generator resolves and validates those numeric args; it does
not expose a public user-name override. The image exposes passwordless
container-local `sudo -n` for mounted dependency installation. This does not
invoke host `sudo`, prompt for a host password, mutate host groups, or add an
AgentCanon-specific group. Workspace bind outputs are expected to carry the host
mapped UID/GID owner.

`devcontainer.json` must not use a fixed AgentCanon display name for every
parent repository. The generated Compose file must also set a top-level project
`name` derived from the repository path, while allowing an explicit
`DEVCONTAINER_PROJECT_NAME` override for rare host-level collisions.
It must not set fixed subnet, gateway, or IPAM values; Docker Compose should
allocate the project network automatically.

依存 source の作業領域は、親 repository root 直下の Git 管理外
`workspace/<topic-slug>/` に置く clone の filesystem / lifecycle として扱います。
親 repository clone と dependency source clone は同じ topic root の直下に置きます。
親 repository の `.gitignore` は `workspace/` を Git 管理外にすることが必須です。
`prepare` の前にこの ignore rule を確認し、満たさない親 repository では
dependency source work を開始しません。

ここでいう topic workspace は filesystem / lifecycle と devcontainer mount の
用語です。VS Code workspace を意味しません。devcontainer は topic workspace
root を一度だけ `/workspace` に bind mountし、`AGENT_CANON_WORKSPACE_ROOT=/workspace`
を固定します。`<parent-repo-root>/workspace/<topic-slug>/<parent-repo>` と
同列の `<module-basename>` clone が host layout です。個別 clone や親 repository
の二重 mount、host absolute path の tracked config への書き込みは行いません。
`/workspace` mount または dependency tool の欠落は startup design error として
post-attach と `tools/ci/container_config.py` が報告します。

Topic workspace の外側にある既存 repository checkout は `direct-repo` layout の
canonical exception として扱います。direct-repo は exact repository root だけを
`/workspace/<basename>` に bind し、親 `~/workspace` 全体、sibling clone、推測した
別 path を mount しません。dependency-module topic marker/status guard は
direct-repo では要求・実行せず、managed-topic では従来どおり必須です。

generator は `AGENT_CANON_WORKSPACE_LAYOUT=managed-topic|direct-repo` を Compose
environment に出力し、post-attach は `DEPENDENCY_MODULE_CONTAINER_LAYOUT`、
`DEPENDENCY_MODULE_CONTAINER_SOURCE`、`DEPENDENCY_MODULE_CONTAINER_TARGET` と
exact source/target を readback します。direct-repo の acceptance command は
`devcontainer up --workspace-folder .` であり、layout env/readback が一致しない、
source が repository root 以外、または sibling/parent workspace が bind された場合は
startup design failure です。

## VS Code surface の責務境界

依存 source clone の表示・構成のために、VS Code multi-root workspace、
`*.code-workspace`、`workspace.json`、その他の editor workspace metadata を
作成、更新、管理、または要求してはなりません。`prepare` が返す
`PARENT_ROOT`、`SOURCE_CLONE`、`CONTINUE_PATH` は filesystem / lifecycle と
devcontainer mount の path contract であり、VS Code workspace の構成入力では
ありません。

この禁止は `.vscode/` の共有 extension/settings/tasks surface を変更しません。
`.vscode/` は親所有の regular directory container とし、template と derived repo
には `vendor/agent-canon/.vscode` の共有ファイルを個別 symlink として公開します。
共有面は推奨 extension、repository 間で安全な editor defaults、共有 validation
task を所有しますが、dependency clone 群の構成責務は所有しません。個人の
editor state、machine-local settings、host-specific path、project/product 固有の
command は共有面に置きません。

## Validation

Changes to this boundary must update and run:

```bash
python3 tools/ci/container_config.py
python3 tools/ci/check_github_workflows.py
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
```

Template or derived repos that consume a new AgentCanon devcontainer pin must
also run:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh link-root
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
make agent-canon-pr-check
make ci
```
