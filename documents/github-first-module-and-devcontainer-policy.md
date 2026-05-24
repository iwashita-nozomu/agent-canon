<!--
@dependency-start
responsibility Documents GitHub-first reusable module and devcontainer ownership policy.
downstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership
downstream design ./coding-conventions-project.md project environment rules
upstream design ../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
downstream environment ../.devcontainer/devcontainer.json shared devcontainer entrypoint
downstream implementation ../tools/ci/container_config.py validates Dockerfile and devcontainer boundaries
@dependency-end
-->

# GitHub-First Modules And Devcontainer Boundary

AgentCanon-owned reusable modules, skills, tools, and runtime surfaces assume a
GitHub source-of-truth path.

The normal route is:

1. Change AgentCanon in a source branch.
1. Open an AgentCanon GitHub PR.
1. Merge to AgentCanon `main` after review and checks.
1. Update template or derived repos by advancing the `vendor/agent-canon`
   submodule pin.
1. Repair root views with `bash tools/sync_agent_canon.sh link-root`.

Local Git remotes and local bare mirrors are compatibility surfaces. They may
support fast local validation or legacy repo migration, but they must not define
the normal distribution path for self-authored reusable modules.

## Local Git Compatibility

Repo-specific local Git problems are deferred to the repo that owns them.
AgentCanon shared architecture must not be shaped around a broken local bare
mirror, a host-only path, or a one-machine remote name.

Allowed compatibility cases:

- an explicitly configured local mirror for faster fetches;
- a temporary GitHub branch prepared from a repo that cannot push directly from its current runtime;
- migration support for a repo that has not completed submodule conversion.

Required boundaries:

- record the GitHub SHA as the canonical evidence;
- record local mirror SHA only when the task uses that mirror;
- keep local mirror names out of shared Dockerfiles and shared default config;
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
- host auth material;
- host workspace, `/mnt/git`, or machine-local mount policy.

If a project genuinely needs Node, npm, or GitHub CLI as part of its own product
runtime, that project must document the product requirement in its repo-local
Docker docs and validation. Agent convenience is not enough.

## Devcontainer Boundary

`.devcontainer/` is AgentCanon-owned runtime ergonomics. Template and derived
repos expose it as a root symlink view into `vendor/agent-canon/.devcontainer`.

The shared devcontainer owns:

- post-create installation of Codex, npm/Node when needed for Codex, and
  GitHub CLI / `gh`;
- post-create installation of agent-side JSON inspection helpers such as `jq`;
- post-create installation of the Rust toolchain, rustfmt, clippy,
  rust-analyzer, and the AgentCanon CLI when the AgentCanon source tree contains
  `rust/agent-canon/Cargo.toml`;
- repository-specific devcontainer and Docker Compose project names, so template
  clones do not all create the same visible container names;
- host auth mount conventions for Codex, GitHub CLI, and SSH;
- optional `/mnt/git` compatibility mounts when the host path exists;
- Docker socket mount detection and reporting;
- workspace attach status reporting;
- agent bootstrap ergonomics that should stay consistent across template
  clones.

The shared devcontainer consumes repo-local Docker runtime contracts instead of
owning them. It reads `docker/packs/default.toml`, builds the repo-local
`docker/Dockerfile`, forwards the pack runtime environment into the generated
Compose service, and runs repo-local `docker/install_python_dependencies.sh`
after the workspace is mounted.

`devcontainer.json` must not use a fixed AgentCanon display name for every
parent repository. The generated Compose file must also set a top-level project
`name` derived from the repository path, while allowing an explicit
`DEVCONTAINER_PROJECT_NAME` override for rare host-level collisions.
It must not set fixed subnet, gateway, or IPAM values; Docker Compose should
allocate the project network automatically.

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
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-pr-check
make ci
```
