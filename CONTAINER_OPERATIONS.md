# Container Operations Rulebook

<!--
@dependency-start
contract reference
responsibility Documents AgentCanon-owned container, devcontainer, editor workspace, and recent cross-repository operation rules.
upstream design README.md AgentCanon top-level entrypoint and rule index.
upstream design documents/runtime/SHARED_RUNTIME_SURFACES.md shared root view and owner-class manifest.
upstream design documents/experiments/gpu-admission-r5-source-packet.md exact GPU admission runtime identity boundary.
downstream design documents/contracts/github-first-module-and-devcontainer-policy.md GitHub-first module and standalone-source/parent devcontainer boundary policy.
downstream design documents/design/rust-agent-tool-migration.md Rust toolchain and AgentCanon CLI migration boundary.
downstream design documents/conventions/coding-conventions-project.md project environment and dependency ownership conventions.
downstream environment agent-canon-environment.toml machine-readable AgentCanon environment contract.
downstream implementation .devcontainer/devcontainer.json standalone AgentCanon devcontainer entrypoint.
downstream implementation .devcontainer/post-create.sh standalone AgentCanon shared post-create lifecycle.
downstream implementation .vscode/settings.json standalone AgentCanon source editor defaults.
downstream implementation tools/ci/container_config.py container and devcontainer configuration validator.
downstream implementation tools/ci/check_github_workflows.py GitHub workflow checkout and Docker-build validator.
@dependency-end
-->

This rulebook is the top-level AgentCanon reference for repositories that vendor
AgentCanon as a submodule. Use it before editing, normalizing, or reformatting
container, devcontainer, or shared editor workspace surfaces in a
template-derived repository.

## Reader Map

- This rulebook owns the AgentCanon Docker, standalone devcontainer/VS Code source, and active root-view boundary.
- `Scope`, `Canonical Source Contract`, and `Ownership Boundary` explain what this file controls; the Dockerfile, devcontainer, Python dependency, GitHub workflow, validation, hook, and recent-rule sections cover the operational details.
- Read it before changing container, devcontainer, editor workspace, Docker workflow, or related validator surfaces.

## Scope

This document is AgentCanon-owned. It describes the shared rule boundary. The
actual project container contract remains repository-local unless the path is one
of the active AgentCanon root views (`AGENTS.md`, `.codex/config.toml`, or
`tools/agent-canon`).

Read this file when a task touches any of these surfaces:

- `.devcontainer/`
- `.vscode/`
- `Dockerfile`
- `docker/`
- `.github/workflows/*docker*`
- `.github/scripts/checkout_agent_canon_submodule.sh`
- `tools/ci/container_config.py`
- `tools/ci/check_github_workflows.py`
- `documents/contracts/github-first-module-and-devcontainer-policy.md`
- `documents/design/rust-agent-tool-migration.md`

## Canonical Source Contract

This file is the source of truth for the Docker / devcontainer / VS Code ownership
boundary. `agent-canon-environment.toml` is the machine-readable environment
contract for Rust tooling, compiled tool cache, MCP preflight commands, and
deterministic search tool locations. Other files may summarize the boundary, but they must
not become a second policy surface.

Use this precedence when wording conflicts:

1. `CONTAINER_OPERATIONS.md`: normative owner boundary, forbidden placements,
   and required validation.
1. `agent-canon-environment.toml`: machine-readable toolchain, compiled tool,
   MCP preflight, and deterministic search environment expectations.
1. `tools/docker_dependency_validator.sh`: mechanical enforcement of the
   boundary for template and derived repos.
1. `docker/README.md`: repo-local implementation runbook for this template's
   runtime packs, Dockerfile, Python dependency installer, and Jupyter/nested
   Codex entrypoints.
1. `Makefile`: command aliases only. Target comments must not redefine policy.
1. skill prompts and coding convention docs: routing summaries that point back
   to this rulebook.

When the boundary changes, update this file first. Then update the validator,
repo-local Docker runbook, Makefile target comments, and skill prompt summaries
only as needed to keep them consistent with this rulebook.

## Ownership Boundary

The ownership boundary covers these primary surfaces.

| Surface                | Owner                          | Rule                                                                                                                                                           |
| ---------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.devcontainer/`       | Template or derived repository | Parent-owned regular environment directory. Standalone AgentCanon owns only its own source checkout; parent regular files are preserved.                   |
| `.vscode/`             | Template or derived repository | Parent-owned regular editor directory. Standalone AgentCanon may validate its four source files; no parent mirror is required.                              |
| `Dockerfile`           | Template or derived repository | Project image contract. Do not add generic Codex, GitHub CLI, Rust toolchain, or agent convenience tooling here.                                               |
| `docker/`              | Template or derived repository | Project-local container runbook, dependency packs, runtime package contract, and repository-specific image policy.                                             |
| GitHub Docker workflow | Template or derived repository | Parent-owned workflow. Its Docker behavior follows this rulebook; any AgentCanon source use is selected by the workflow rather than materialized as a root copy. |

The separation is intentional. AgentCanon owns the shared automation boundary;
the repository owns its runtime image and product dependencies.

## Product Image And Mounted Tool Boundary

`Dockerfile` and `docker/` describe the product image build/runtime contract:
project libraries, compilers, native build inputs, service processes, and
workspace Python dependency policy. They must not acquire Codex, GitHub CLI,
Node/npm, Rust, Lean, Playwright, or other shared agent tooling solely for
developer convenience.

The mounted workspace devcontainer contract is separate. The standalone image
installs fixed OS/Python capabilities directly in its Dockerfile. Node/npm
22.14.0/10.9.2 is owned by the exact digest-pinned Node devcontainer Feature.
`.devcontainer/dependencies.toml` then describes the small default set of
mounted developer/agent tools. Browser, TeX/PDF, proof, full Rust, and security
scanner capabilities are selected by their owning workflow or CI image rather
than installed by every default startup.

In a derived repository, the parent overlay and final hook are optional:
`.devcontainer/dependencies.toml` is read only when present, and its absence
means no parent dependency overlay; `.devcontainer/post-create-parent.sh` is
called only when present, and its absence means no parent final hook. The
legacy parent-environment pair is likewise optional and is audited only when
present. No empty sentinel, disabled marker, or no-op wrapper is required.
The standalone-source post-create invoked via the source-root resolver validates the available sources, merges a present parent
manifest before the canonical AgentCanon manifest, validates the complete graph,
and executes it only after that validation succeeds.

## Manifest Source Roles And Cardinality

Schema v2 uses structured manifest-source roles rather than filename guesses.
In a parent-plus-vendor layout, `<workspace>/.devcontainer/dependencies.toml`
is the optional `parent-overlay` source when present. Its absence means no
parent-owned derived tools. New derived repositories must not create an empty
manifest or sentinel for that case; they leave the optional overlay absent.
For migration compatibility, the parser still accepts an existing present
overlay that explicitly declares `records = []`. The
`vendor/agent-canon/.devcontainer/dependencies.toml` source is `canonical` and
must remain non-empty. In standalone AgentCanon, the workspace manifest is
also `canonical` and must remain non-empty. After source loading, the merged
plan must contain at least one record. Provider, missing-dependency, cycle, and
typed-verification invariants are unchanged.

The parent-owned `pyproject.toml` is the owner of workspace Python packages.
Runtime packs declare ordered `runtime.dependency_extras` (default `[]`), and
the generated environment serializes them only at the boundary as
`AGENT_CANON_PYTHON_EXTRAS=extra,...`. When selected, shared post-create validates
the extras against `project.optional-dependencies`, performs one standard
editable install with current Python/pip, and runs `pip check`.
## Dockerfile Rules

Keep the project `Dockerfile` focused on the project runtime.

- Install OS packages that the project runtime, tests, build system, or native
  dependencies require.
- Keep `python3`, `pip`, compilers, and build tools only when the project needs
  them.
- Do not install Codex CLI, GitHub CLI, `gh`, Node.js, or npm solely for agent
  convenience.
- Do not install rustup or run cargo solely for AgentCanon CLI or shared
  analysis-tool migration work.
- Do not install `elan`, Lean, Lake, or proof-search tooling solely for
  AgentCanon formal-proof workflows.
- Do not install TeX / LaTeX tooling solely for Academic Writing agent output.
- Do not bake host-specific mount paths such as `/mnt/git` into the image.
- Do not install repository Python dependencies during image build when those
  dependencies depend on the mounted workspace.
- Do not add fixed AgentCanon capability to a project product Dockerfile;
  standalone AgentCanon `.devcontainer/Dockerfile` owns fixed OS/Python
  capability, while the digest-pinned official Node Feature owns Node/npm.

If a project genuinely needs Node.js, npm, GitHub CLI, Rust, or another
agent-looking tool as a product/runtime dependency, document that as a
repository-local requirement in `docker/README.md` and validate it through the
project CI path.

## Devcontainer Rules

Use the parent-owned `.devcontainer/` surface for project and agent runtime setup.

- Codex CLI, GitHub CLI, `gh`, Node.js used only by Codex or agent tooling,
  JSON and structure inspection helpers such as `jq` and `tree`, and other
  shared developer/agent tools belong in `.devcontainer/dependencies.toml`.
  Fixed OS/Python capabilities are image-owned, Node/npm is supplied by the
  digest-pinned official Node Feature, and the typed dependency engine is
  invoked by `.devcontainer/post-create.sh`; package versions are not
  overridden by environment variables.
- `tree` is the canonical agent-side structure inspection display for template
  and derived parent repo readiness. Use
  `tree -a -L <depth> -I '.git|__pycache__|.venv|node_modules|target|reports' <parent-root>`
  with `tools/agent_tools/parent_repo_readiness.py` when checking root view
  shape; do not require parent repositories to commit generated `tree` output
  unless a task-specific design explicitly asks for that artifact.
- Codex CLI setup is a pinned `npm-global` record for `@openai/codex` 0.145.0
  with an exact npm package identity and executable verification contract.
- Every dependency record has one method-compatible typed verification
  contract. A matching receipt is reusable only while that contract proves the
  current owner artifact. Missing package files, apt repository key/source
  files, executables, toolchains, browser cache targets, or built Cargo
  binaries invalidate the receipt and enter method-specific repair installation
  before a new receipt is written.
- Public-repository security scanners, browser automation, TeX/PDF, proof
  toolchains, and full Rust tooling are opt-in workflow or CI capabilities.
  Their records and caches must not be added to the default manifest merely to
  make those workflows available in every project. A selected workflow owns
  its external/on-demand installation and typed verification route.
- Shared C/C++ formatting tooling, including `clang-format`, belongs in one
  typed `apt-package` record in `.devcontainer/dependencies.toml` when it is
  only needed for shared AgentCanon tooling. The manifest owns installation,
  package version, and executable verification; it is agent-side formatting
  infrastructure, not a project runtime dependency. The record's package
  source and version must match the current Ubuntu image contract rather than
  a copied historical distro literal. The `apt-package` receipt trust boundary
  is the package manager database: `dpkg-query --show` must report
  `install ok installed`, the exact declared version, and the declared package
  identity, followed by any typed record-owned executable/version check. Raw
  `dpkg --verify` output is not a blocking oracle because official Ubuntu
  images may intentionally exclude documentation and manpage payloads.
- LSP language servers used by shared code analysis are mounted
  developer/agent tools and belong in typed manifest records, never in a
  product Dockerfile. The canonical records pin Pyright 1.1.411, Bash
  Language Server 5.6.0, `clangd-18` from the signed Jammy LLVM repository,
  and Rust 1.89.0 with `rust-src` and `rust-analyzer`. `python`, `c`/`cpp`,
  `shellscript`, and `rust` resolve to the verified commands
  `pyright-langserver --stdio`, `clangd-18`, `bash-language-server start`,
  and `rust-analyzer`; ambient PATH discovery is not a substitute for a
  manifest record.
- An `apt-repository` record declares its typed suite and components. When it
  carries `repository_packages_sha256`, the installer derives the canonical
  uncompressed Packages URL from source, suite, component, and `platform`,
  downloads it, and fails closed on a missing or mismatched digest before the
  repository is accepted. A record may additionally carry the paired
  `repository_package_url` and `repository_package_sha256` immutable `.deb`
  identity; the installer downloads that exact artifact, verifies its SHA-256,
  then installs the local file while retaining dependency resolution through
  the signed repository. Its signed source line and any declared executable
  verification are read back exactly; the rolling Packages digest and
  immutable artifact digest are separate receipt fields.
- A successful dependency receipt atomically records the plan/record
  fingerprints, verification contract, and `executable_bindings` for every
  provided LSP binary. `resolve_verified_executable(workspace, vendor_root,
  receipts, record_id, executable)` accepts a binary only after the exact
  record and receipt match, the installer performs live method-specific
  verification, the current absolute executable path is resolved, and both
  path and verification-output identity match the receipt. npm records bind
  `pyright` and `pyright-langserver` to the same package; apt binds the
  declared executable owner package set's lexical/resolved paths from
  `/usr/bin/dpkg-query --listfiles` ownership output; Rust binds the pinned
  toolchain's `rust-analyzer` path. Ambient `PATH` or `shutil.which` never
  participates.
- Lean/proof and TeX/PDF tooling are selected workflow capabilities. When a
  proof or writing workflow needs them, its owning CI image or on-demand pack
  declares the same typed records and checksums; these records are not part of
  the default manifest.
- Structured analysis cache rebuilds remain warning-only when an external or
  selected AgentCanon CLI is available. Default startup does not build Rust or
  require a Cargo record, so an unavailable CLI simply skips the cache rebuild.
- Model server, installer, model-cache, and compatibility consumers are not
  part of the container runtime. Former compatibility validation is a read-only
  `skill_evaluator` route using `gpt-5.4-mini`; the container does not download,
  start, or mount a local model runtime.
- Compiled agent convenience binaries belong under
  `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}`. `/usr/local/bin` may contain
  symlinks for stable command discovery, but the compiled binary cache itself
  must not live in the project Dockerfile or tracked repository tree.
- Devcontainer post-create must publish Rust on PATH for non-interactive
  `devcontainer exec` commands, not only for the current post-create shell.
- AgentCanon pin updates must refresh the compiled AgentCanon CLI after the new
  source is checked out. The canonical path is `tools/rebuild_agent_tools.sh`,
  called by `make agent-canon-ensure-latest`, `make agent-canon-latest`, and
  `make agent-canon-update`.
- Runtime state and logs are container-local under
  `/var/lib/agent-canon/runtime`; only the controlled source-bound projection
  under `/workspace/reports/agents/<run-id>/runtime` is copied to the workspace.
  Default Compose creates this path inside the container; it is not a host bind or
  shared-runtime path.
- The default repository Docker pack uses the #524 canonical digest-pinned plain
  `ubuntu:22.04` base. The generator resolves and validates `PROJECT_UID` /
  `PROJECT_GID` build args; the parent image creates the canonical `project`
  user/group with those IDs and runs as `USER project`. Linked `devcontainer.json`
  sets `containerUser` and `remoteUser` to `project`; the generator omits custom
  HOME tmpfs and AgentCanon-specific groups. `/home/project` remains the
  image-owned HOME. Container-local passwordless `sudo -n` is available for
  mounted dependency operations.
- This project runtime is container-local and never invokes host `sudo`, prompts for
  host passwords, or mutates host groups. A missing/mismatched project UID/GID,
  non-Ubuntu base, missing digest pin, or missing container-local sudo is a parent image
  contract failure; do not repair it by restoring host provisioning. Workspace bind
  outputs are expected to carry the host mapped UID/GID owner.
- Devcontainers support two explicit source layouts. `managed-topic` keeps the
  `workspace/<topic-slug>` workspace-root bind and dependency-module topic
  marker/status guard. `direct-repo` binds only the exact repository root to
  `/workspace/<basename>`; it does not mount the parent `~/workspace`, sibling
  repositories, or guessed paths, and it does not require or run the topic
  marker/status guard. The generator emits `AGENT_CANON_WORKSPACE_LAYOUT`, and
  post-attach reads back `DEPENDENCY_MODULE_CONTAINER_LAYOUT` with the same value plus
  `DEPENDENCY_MODULE_CONTAINER_SOURCE` and `DEPENDENCY_MODULE_CONTAINER_TARGET` exact
  source/target fields. The direct path is validated by
  `devcontainer up --workspace-folder .`.
  Host `~/.codex` is never mounted. Successful post-create tool availability is
  recorded and later certified by `EnvironmentCertificate`, not by a second
  environment policy surface.
- Nested Codex uses container-local state under the selected workspace runtime
  home for Codex session semantics, but the runner sets the profile-scoped
  `XDG_STATE_HOME=/tmp/agent-canon-xdg-state/<profile>` outside the workspace
  so shared post-create dependency receipts remain container-local. The runner
  may forward `OPENAI_API_KEY` and `OPENAI_BASE_URL` explicitly; it never
  mounts or seeds host Codex state.
- 既定 devcontainer は GPU admission の host runtime identity を要求しない。
  固定 OS/Python capability は image、Node/npm は digest-pinned Feature が所有し、
  `finalize-shared-runtime.sh`、shared lock、provision/readback receipt は GPU
  admission の明示 lifecycle に保持する。既定の linked config からは GPU runtime
  を選択せず、experiment scheduler や managed experiment の wholesale deletion を
  意味しない。
- GPU admission を使う場合は親-owned regular `.devcontainer/gpu-admission/devcontainer.json`
  を selector とする `.devcontainer/gpu-admission.sh` を明示実行する。derived repository
  へ AgentCanon の child symlink は投影せず、親が必要な entrypoint を source-root
  resolver 経由で選択する。standalone AgentCanon では同じ resolver を
  `tools/agent_tools/agent_canon_source_root.py` から実行する。profile は
  `nvidia-smi -L`、`devcontainer` CLI、active repository を fail-closed に確認した後、
  `${repository_root}/.agent-canon/runtime` を primary UID/GID 所有で作成し、
  provision receipt を発行する。GPU 不在、provision receipt 不一致、Compose/up/finalize
  failure は default profile へ降格しない。host `sudo`、system group 作成、session
  refresh はこの lifecycle の前提ではない。
- `gpu-admission.sh` は repository-local source/provision receipt を profile generator
  へ渡す。profile Compose は host
  `${repository_root}/.agent-canon/runtime` を container の
  `/var/lib/agent-canon/runtime` へ bind し、primary `PROJECT_UID:PROJECT_GID`、
  `gpus: all`、`DEVCONTAINER_GPU_MODE=enabled`、
  `DEVCONTAINER_GPU_REQUEST=all`、`MANAGED_CONTAINER` route を出力する。default
  Compose はこれらを出力しない。profile output は
  `.agent-canon/gpu-admission-compose.generated.yml`、project identity は
  `-gpu-admission` suffix とし、起動済み default container を再利用しない。
- `devcontainer up` の成功後、同じ orchestrator が同じ profile `--config` の
  `devcontainer exec` と source-root resolver で `finalize-shared-runtime.sh` を一度だけ
  実行する。finalize は provision receipt、
  bind device/inode、mount namespace、probe、repository-local source、primary UID/GID、
  umask を検証し、
  `shared-runtime-readback.json` を `tools/experiments/execution_resource_plan.py` の
  `read_shared_runtime_provision` / `write_runtime_receipt_atomic` owner 経由で発行する。
  profile script は receipt parser/writer や identity repair を複製しない。
- up/finalize failure は生成 Compose の検証済み `-gpu-admission` project name と
  profile-specific Compose file を指定して `docker compose down --remove-orphans` を
  実行する。cleanup failure は typed evidence として別に報告し、entrypoint は元の
  up/finalize rc を保持する。
- GPU-admission profile を選択しない限り、`/var/lib/agent-canon/runtime` の
  `shared-runtime-provision.json` / `shared-runtime-readback.json` を default の
  Compose environment、bind、post-create、post-attach の前提にしてはならない。
  Receipt parsing と atomic publication の owner は引き続き
  `tools/experiments/execution_resource_plan.py` とし、scripts に第二の parser/writer
  や identity repair を追加しない。
- Mount behavior belongs in `.devcontainer/devcontainer.json`.
- Devcontainer names must be repository-specific. Do not use a fixed
  `name` or Compose project name that makes every template-derived repository
  create the same visible devcontainer/container names.
- The generated Docker Compose file must set a top-level project `name` derived
  from the repository path, with `DEVCONTAINER_PROJECT_NAME` reserved as an
  explicit override for rare host-level collisions.
- The generated Docker Compose file must not pin subnet, gateway, or other
  IPAM values. Let Docker Compose allocate the default network automatically so
  multiple checkouts and host networks do not collide.
- 既定 profile は host GPU、`nvidia-smi`、Docker NVIDIA runtime を probe せず、生成
  environment に `DEVCONTAINER_GPU_MODE=disabled` を設定する。`DEVCONTAINER_GPU_REQUEST`
  は absent とし、`gpus: all` も生成しない。GPU が見える host でも default Compose
  は GPU runtime を自動追加せず、GPU 不在を default container creation の分岐条件に
  しない。GPU を必要とする実験の explicit profile owner は
  `.devcontainer/gpu-admission.sh` と profile selector であり、既定境界は本 rulebook
  と linked implementation が所有する。
- Host authentication must stay host-local. The container may reuse mounted
  credentials, but the Docker image must not bake user tokens or auth state.
- `safe.directory` setup must be dynamic for `/workspace` and
  `/workspace/vendor/<name>`.
- `/mnt/git` is compatibility-only and is never a default bind. Select the typed
  `host-git` optional profile only when the host path exists.
- A private host directory for confidential local Git repositories or other
  operator-local material may be mounted only through
  `AGENT_CANON_SECRET_DIR`. The shared generator must skip the mount when the
  profile is absent, the variable is unset, or the path is absent, and must use
  the fixed container target `/mnt/agent-canon-secrets`. Any custom
  `AGENT_CANON_SECRET_MOUNT` target is rejected. Use
  `AGENT_CANON_SECRET_DIR_MODE=rw` only when the container must update local
  Git remotes; otherwise keep the default read-only mode.
- Resolver-invoked standalone-source post-create logic must tolerate a repository that has no local bare
  mirror and no host-specific optional mount.
- Devcontainer-generated Compose must forward repo-local runtime environment
  entries from `docker/packs/default.toml` so editor kernels, shells, and smoke
  commands share the same import root.

## Python Dependency Rules

Repository Python dependencies are mounted-workspace state, not Docker image
state.

- Select `runtime.dependency_extras` in the pack when project packages are needed;
  `post-create.sh` installs them from the parent `pyproject.toml` when present.
- Shared post-create passes dependency receipts to the container-local
  `${XDG_STATE_HOME:-$HOME/.local/state}/agent-canon/dependency-receipts` path;
  it validates that the state root is absolute and outside the workspace before
  the installer creates it. Receipts never use the workspace's `.agent-canon`
  bind state, so rootless mapped users can write them without changing host
  ownership. The generic dependency CLI fallback remains available for direct
  callers that do not select the shared post-create path.
- Host runtime does not create a repository-local virtual environment.
- Container runtime may create `.venv` only through the canonical policy tool:

```bash
python3 tools/ci/python_env_policy.py --create
```

- Do not create `venv/`, `env/`, `.conda/`, or ad hoc environment directories.
- Dependency packs under `docker/packs/` are repository-local contracts and must
  not be treated as AgentCanon shared policy.

## GitHub Workflow Rules

Any GitHub workflow that runs shared AgentCanon devcontainer checks must checkout
the AgentCanon submodule before calling shared AgentCanon paths.

Required pattern:

1. Checkout the repository with `submodules: false` and `persist-credentials: false`.
1. Run `.github/scripts/checkout_agent_canon_submodule.sh`.
1. Provide exactly one private AgentCanon credential source when private access is
   needed:
   - `AGENT_CANON_REPO_TOKEN`
   - `AGENT_CANON_REPO_SSH_KEY`
1. Run Docker or devcontainer smoke after `vendor/agent-canon/` exists.

Old wording that describes Docker Build as "submodule-free" is stale. Replace it
with the submodule-aware pattern above.

## Reformatting Checklist

When normalizing a repository that has `vendor/agent-canon/`, run this checklist
before editing.

| Step | Required check                                                                                                                             |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Classify each touched path as AgentCanon-owned, template-owned, parent-owned regular content, or one of the three active root views.       |
| 2    | Check the AgentCanon submodule pin and repair only the three active root views with the request-evidence-authorized source-root resolver `exec tools/sync_agent_canon.sh link-root` route when needed. |
| 3    | Move agent convenience installs out of `Dockerfile` and into the parent-owned `.devcontainer/post-create.sh` when they are not product dependencies. |
| 4    | Keep workspace-dependent Python package installation in `pyproject.toml` optional extras and the shared post-create lifecycle.       |
| 5    | Ensure Docker workflows checkout `vendor/agent-canon/` before parent devcontainer smoke.                                                   |
| 6    | Update `docker/README.md`, top-level README links, and workflow comments that still assume older ownership rules.                          |
| 7    | Run the validators listed below and record any skipped command with reason and owner.                                                      |

## Required Validation

For container or devcontainer changes, use the targeted checks first and then the
repository closeout checks.

```bash
python3 tools/ci/container_config.py
python3 tools/ci/check_github_workflows.py
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
make agent-canon-pr-check
```

In template-derived repositories, also run the repository-native checks after the
AgentCanon pin or root views change:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
    exec tools/sync_agent_canon.sh link-root
make docker-build-check
make ci
```

If the repository uses GitHub Actions for Docker evidence, the Docker Build
workflow result may stand in for `make docker-build-check` only when the workflow
uses the submodule-aware checkout pattern in this rulebook.

## Hook And Log Rules

Hook output is evidence, not a decoration.

- Hook invocation logs under `.agent-canon/log-archive/hook-runs/**/*.jsonl` are
  AgentCanon-owned append-only evidence artifacts in the external log archive,
  not product source files.
- Do not stash, drop, or revert hook-run JSONL as "generated noise" to make a
  submodule look clean. If the log is too noisy, fix the hook filter or
  route the observation through an AgentCanon PR; do not hide the evidence.
- Repeated OOP readability failures must stop the implementation path until the
  changed code or the hook rule is corrected.
- Runtime-local `reports/hooks/` output is temporary only when a task explicitly
  overrides the hook destination. The default AgentCanon hook result surface is
  durable.
- Read-only, checker-only, and no-source hook invocations should be filtered by
  the hook before writing if they are not intended as durable evidence. Once a
  tracked AgentCanon hook-run line exists, treat it as evidence until a retention
  pass explicitly compacts it.
- An empty or alternate route hook payload that still evaluates changed source must be
  logged with the payload status, not silently treated as success.
- Skill and workflow eval results must receive unique IDs and append-only result
  files. Do not overwrite detailed eval evidence.
- A historical hook failure may remain in append-only logs, but a current task
  must confirm the latest hook invocation state before claiming the hook is fixed.

## Recent AgentCanon Rule Changes

These are the latest ten merged AgentCanon PRs that changed operational rules or
the tooling that enforces them. Merge times are GitHub `mergedAt` values in UTC.

| PR            | Merge            | Rule change for downstream repositories                                                                                                           |
| ------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| #17 `9241cbd` | 2026-05-13 14:47 | Docker devcontainer CI must checkout AgentCanon before parent devcontainer smoke. The workflow checker rejects the old submodule-free assumption. |
| #16 `0de03e4` | 2026-05-13 14:28 | Hook, skill, eval, memory, issue, and improvement-guide evidence must accumulate through explicit files and workflow gates.                       |
| #14 `dfd0b6d` | 2026-05-13 13:29 | Nested Codex post-create setup belongs in the resolver-invoked standalone-source path and runs after the workspace is available.                                 |
| #13 `d679446` | 2026-05-13 13:36 | Helper inventory supports changed-file baseline mode; new helpers require reuse evidence and changed-scope inspection.                            |
| #12 `c5a7c77` | 2026-05-13 13:12 | GitHub-first custom modules and standalone-source/parent devcontainer ownership are the default; local Git mirrors are compatibility-only.                          |
| #11 `62d8342` | 2026-05-13 12:57 | Helper definitions must be inventoried and justified instead of added as untracked convenience code.                                              |
| #10 `d8caa5b` | 2026-05-13 12:15 | Review backlog and repo-wide scans must degrade when `rg` is missing instead of assuming one local search tool.                                   |
| #9 `2da3793`  | 2026-05-13 12:01 | PR queue cleanup requires validation gates and authority evidence before mutation.                                                                |
| #8 `7f512e3`  | 2026-05-13 11:50 | PR mutation authority is explicit. `gh` availability alone does not authorize merge, close, or branch delete.                                     |
| #7 `0856d16`  | 2026-05-13 11:06 | OOP hook alternate route payloads must be logged with unique evidence rather than disappearing into a generic pass/fail result.                   |

## Recent Template Rule Changes

The template repository currently has fewer than ten merged GitHub PRs, so this
table uses the latest ten rule-affecting `main` commits. Use it when reformatting
a template-derived repository that may still contain stale wording.

| Commit    | Rule change for template-derived repositories                                                                                           |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `d68f736` | Template now adopts the shared AgentCanon devcontainer and Agent Improvement Guide workflow.                                            |
| `3715e3d` | Template pinned the AgentCanon operational issue and inspection proposal; issue evidence is part of workflow state.                     |
| `b5c8368` | GitHub CI installs `ripgrep`; repo-wide search tooling may prefer `rg` but must still document alternate route behavior where required. |
| `58d3e18` | AgentCanon snapshot sync: root shared views are repaired by sync tooling, not edited as independent truth surfaces.                     |
| `8ee9867` | AgentCanon snapshot sync: downstream template changes must carry the submodule pin evidence.                                            |
| `d597611` | AgentCanon snapshot sync: template root views track the AgentCanon pin and must not assume subtree ownership.                           |
| `6c0dc6b` | Template pinned PR authority evidence from AgentCanon; branch and PR mutation require explicit workflow evidence.                       |
| `927f604` | Template pinned the PR authority proposal; GitHub operations are part of the documented agent workflow.                                 |
| `8efa2ad` | Template pinned repo-cross inspection updates; search hits should be expanded into edit-scope dependency lists.                         |
| `669cc4d` | Template pinned the operational issue gate proposal; operational findings must have durable issue-file evidence.                        |

## Stale Rule Sweep

When a repository is being reformatted against current AgentCanon rules, sweep for
these stale assumptions:

- "Docker Build is submodule-free."
- "AgentCanon is vendored as a subtree or committed snapshot" as the normal path.
- "Local Git mirror is required" for default module work.
- "Root `documents/` is entirely project-local" when shared policy symlinks are present.
- "Hook failure only blocks at closeout" instead of stopping the implementation
  path when it can cause code-generation mistakes.
- "Skill eval results may be overwritten" instead of accumulated with unique IDs.
- "PR mutation is allowed because `gh` is installed."

If a stale rule appears in a human-facing document, update the document and the
dependency header in the same change. If it appears in tooling help text, update
the validator or script output as part of the same rule change.
