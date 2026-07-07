# Container Operations Rulebook

<!--
@dependency-start
contract reference
responsibility Documents AgentCanon-owned container, devcontainer, editor workspace, and recent cross-repository operation rules.
upstream design README.md AgentCanon top-level entrypoint and rule index.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared root view and owner-class manifest.
downstream design documents/github-first-module-and-devcontainer-policy.md GitHub-first module and shared devcontainer boundary policy.
downstream design documents/rust-agent-tool-migration.md Rust toolchain and AgentCanon CLI migration boundary.
downstream design documents/coding-conventions-project.md project environment and dependency ownership conventions.
downstream environment agent-canon-environment.toml machine-readable AgentCanon environment contract.
downstream implementation .devcontainer/devcontainer.json shared AgentCanon devcontainer entrypoint.
downstream implementation .devcontainer/post-create.sh shared AgentCanon post-create bootstrap.
downstream implementation .vscode/settings.json shared AgentCanon VS Code workspace defaults.
downstream implementation tools/ci/container_config.py container and devcontainer configuration validator.
downstream implementation tools/ci/check_github_workflows.py GitHub workflow checkout and Docker-build validator.
@dependency-end
-->

This rulebook is the top-level AgentCanon reference for repositories that vendor
AgentCanon as a submodule. Use it before editing, normalizing, or reformatting
container, devcontainer, or shared editor workspace surfaces in a
template-derived repository.

## Reader Map

- This rulebook owns the AgentCanon Docker, devcontainer, VS Code, and shared editor workspace boundary.
- `Scope`, `Canonical Source Contract`, and `Ownership Boundary` explain what this file controls; the Dockerfile, devcontainer, Python dependency, GitHub workflow, validation, hook, and recent-rule sections cover the operational details.
- Read it before changing container, devcontainer, editor workspace, Docker workflow, or related validator surfaces.

## Scope

This document is AgentCanon-owned. It describes the shared rule boundary. The
actual project container contract remains repository-local unless the path is an
AgentCanon shared root view.

Read this file when a task touches any of these surfaces:

- `.devcontainer/`
- `.vscode/`
- `Dockerfile`
- `docker/`
- `.github/workflows/*docker*`
- `.github/scripts/checkout_agent_canon_submodule.sh`
- `tools/ci/container_config.py`
- `tools/ci/check_github_workflows.py`
- `documents/github-first-module-and-devcontainer-policy.md`
- `documents/rust-agent-tool-migration.md`

## Canonical Source Contract

This file is the source of truth for the Docker / devcontainer / VS Code ownership
boundary. `agent-canon-environment.toml` is the machine-readable environment
contract for Rust tooling, compiled tool cache, MCP preflight commands, and
local LLM tool locations. Other files may summarize the boundary, but they must
not become a second policy surface.

Use this precedence when wording conflicts:

1. `CONTAINER_OPERATIONS.md`: normative owner boundary, forbidden placements,
   and required validation.
2. `agent-canon-environment.toml`: machine-readable toolchain, compiled tool,
   MCP preflight, and local LLM environment expectations.
3. `tools/docker_dependency_validator.sh`: mechanical enforcement of the
   boundary for template and derived repos.
4. `docker/README.md`: repo-local implementation runbook for this template's
   runtime packs, Dockerfile, Python dependency installer, and Jupyter/nested
   Codex entrypoints.
5. `Makefile`: command aliases only. Target comments must not redefine policy.
5. skill prompts and coding convention docs: routing summaries that point back
   to this rulebook.

When the boundary changes, update this file first. Then update the validator,
repo-local Docker runbook, Makefile target comments, and skill prompt summaries
only as needed to keep them consistent with this rulebook.

## Ownership Boundary

The ownership boundary covers these primary surfaces.

| Surface | Owner | Rule |
| --- | --- | --- |
| `.devcontainer/` | AgentCanon | Shared runtime view. Keep common Codex, GitHub CLI, Rust toolchain, mount, and post-create behavior here. |
| `.vscode/` | AgentCanon | Shared editor workspace view. Keep common AgentCanon recommendations, safe defaults, and validation tasks here. |
| `Dockerfile` | Template or derived repository | Project image contract. Do not add generic Codex, GitHub CLI, Rust toolchain, or agent convenience tooling here. |
| `docker/` | Template or derived repository | Project-local container runbook, dependency packs, runtime package contract, and repository-specific image policy. |
| GitHub Docker workflow | Mixed | Workflow file may be GitHub path-constrained copy, but its Docker behavior must follow this rulebook and checkout AgentCanon before shared devcontainer smoke. |

The separation is intentional. AgentCanon owns the shared automation boundary;
the repository owns its runtime image and product dependencies.

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
- Do not make Dockerfile changes to repair AgentCanon post-create behavior.

If a project genuinely needs Node.js, npm, GitHub CLI, Rust, or another
agent-looking tool as a product/runtime dependency, document that as a
repository-local requirement in `docker/README.md` and validate it through the
project CI path.

## Devcontainer Rules

Use the shared `.devcontainer/` surface for agent runtime setup.

- Codex CLI, GitHub CLI, `gh`, Node.js used only by Codex or agent tooling,
  JSON and structure inspection helpers such as `jq` and `tree`, and
  post-create bootstrap belong in `.devcontainer/post-create.sh`.
- `tree` is the canonical agent-side structure inspection display for template
  and derived parent repo readiness. Use
  `tree -a -L <depth> -I '.git|__pycache__|.venv|node_modules|target|reports' <parent-root>`
  with `tools/agent_tools/parent_repo_readiness.py` when checking root view
  shape; do not require parent repositories to commit generated `tree` output
  unless a task-specific design explicitly asks for that artifact.
- Codex CLI setup validates `codex --version` before returning. Command absence
  or a broken wrapper triggers the canonical `npm install -g @openai/codex`
  install command during post-create.
- Public-repository security scanners used by agents, including `gitleaks`,
  `trufflehog`, and `detect-secrets`, belong in `.devcontainer/post-create.sh`.
  They are audit tooling, not project runtime dependencies, and must not be
  installed in the project Dockerfile unless a project explicitly needs them at
  runtime.
- Browser automation tooling used by agents to validate generated HTML and
  JavaScript report artifacts, including Playwright and its Chromium browser
  cache, belongs in `.devcontainer/post-create.sh`. It is report-validation
  infrastructure, not a project runtime dependency.
- Rust, cargo, rustfmt, clippy, rust-analyzer, and the AgentCanon Rust CLI
  belong in `.devcontainer/post-create.sh` when they are only needed for shared
  AgentCanon tooling.
- Lean theorem-proving tooling used by formal-proof skills, including
  `elan`, Lean, Lake, and the default `AGENT_CANON_LEAN_TOOLCHAIN`, belongs
  in `.devcontainer/post-create.sh` when it is only needed for AgentCanon
  proof tooling. Install `elan` from a pinned release asset with a recorded
  SHA256 checksum, not by piping a moving installer script. It is agent-side
  proof infrastructure, not a project runtime dependency.
- Structured analysis cache rebuilds belong in `.devcontainer/post-create.sh`
  after the AgentCanon Rust CLI is installed. The rebuild uses
  `agent-canon structured-analysis build --root <workspace> --profile
  devcontainer`, writes only to
  `${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}`,
  materializes `prose_graph.sqlite` plus a separate `diagnostics.sqlite` warning
  DB, and must be warning-only so container creation continues when the cache
  can be regenerated later.
- TeX document and image tooling used by the Academic Writing skill, including
  `latexmk`, pdfLaTeX, XeLaTeX, TikZ packages, `dvisvgm`, `pdfcrop`,
  Ghostscript, and PDF inspection helpers, belongs in `.devcontainer/post-create.sh`.
  This is an agent-side writing toolchain, not a default project runtime
  dependency.
- llama.cpp and the default 3B-class local LLM model selector belong in
  `.devcontainer/post-create.sh` and `tools/install_llama_cpp.sh` when they are
  used only for AgentCanon local LLM analysis. This local LLM surface is
  CPU-only even on GPU hosts; do not enable CUDA, HIP, Metal, Vulkan, or SYCL for
  `agent-canon local-llm`, including through extra CMake flags.
- Compiled agent convenience binaries belong under
  `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}`. `/usr/local/bin` may contain
  symlinks for stable command discovery, but the compiled binary cache itself
  must not live in the project Dockerfile or tracked repository tree.
- Devcontainer post-create must publish Rust on PATH for non-interactive
  `devcontainer exec` commands, not only for the current post-create shell.
- AgentCanon pin updates must refresh compiled AgentCanon tools after the new
  source is checked out. The canonical path is `tools/rebuild_agent_tools.sh`,
  called by `make agent-canon-ensure-latest`, `make agent-canon-latest`, and
  `make agent-canon-update`. That rebuild path also recompiles an existing
  `${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/src/llama.cpp` checkout so local LLM
  binaries track the updated AgentCanon tool contract.
- Mount behavior belongs in `.devcontainer/devcontainer.json`.
- Shared devcontainer names must be repository-specific. Do not use a fixed
  `name` or Compose project name that makes every template-derived repository
  create the same visible devcontainer/container names.
- The generated Docker Compose file must set a top-level project `name` derived
  from the repository path, with `DEVCONTAINER_PROJECT_NAME` reserved as an
  explicit override for rare host-level collisions.
- The generated Docker Compose file must not pin subnet, gateway, or other
  IPAM values. Let Docker Compose allocate the default network automatically so
  multiple checkouts and host networks do not collide.
- GPU discovery is best-effort and notification-only by default. The generated
  Compose file may include `gpus: all` only when the host GPU and Docker NVIDIA
  runtime are both visible, or when `DEVCONTAINER_GPU_REQUEST=enabled` can be
  satisfied. Missing GPU access must not fail container creation in the default
  path; it should be reported in the generated status and post-attach banner.
- Host authentication must stay host-local. The container may reuse mounted
  credentials, but the Docker image must not bake user tokens or auth state.
- `safe.directory` setup must be dynamic for `/workspace` and
  `/workspace/vendor/<name>`.
- `/mnt/git` is compatibility-only. Configure it only when the host path exists.
- A private host directory for confidential local Git repositories or other
  operator-local material may be mounted only through
  `AGENT_CANON_SECRET_DIR`. The shared generator must skip the mount when the
  variable is unset or the path is absent, must not print the host path, and must
  use `AGENT_CANON_SECRET_MOUNT` for the container target
  (`/mnt/agent-canon-secrets` by default). Use
  `AGENT_CANON_SECRET_DIR_MODE=rw` only when the container must update local
  Git remotes; otherwise keep the default read-only mode.
- Shared post-create logic must tolerate a repository that has no local bare
  mirror and no host-specific optional mount.
- Devcontainer-generated Compose must forward repo-local runtime environment
  entries from `docker/packs/default.toml` so editor kernels, shells, and smoke
  commands share the same import root.

## Python Dependency Rules

Repository Python dependencies are mounted-workspace state, not Docker image
state.

- Use `docker/install_python_dependencies.sh` after the workspace is mounted.
- `post-create.sh` may call the repository-local installer when present.
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
2. Run `.github/scripts/checkout_agent_canon_submodule.sh`.
3. Provide exactly one private AgentCanon credential source when private access is
   needed:
   - `AGENT_CANON_REPO_TOKEN`
   - `AGENT_CANON_REPO_SSH_KEY`
4. Run Docker or devcontainer smoke after `vendor/agent-canon/` exists.

Old wording that describes Docker Build as "submodule-free" is stale. Replace it
with the submodule-aware pattern above.

## Reformatting Checklist

When normalizing a repository that has `vendor/agent-canon/`, run this checklist
before editing.

| Step | Required check |
| --- | --- |
| 1 | Classify each touched path as AgentCanon-owned, template-owned, project-owned, or GitHub path-constrained copy. |
| 2 | Check the AgentCanon submodule pin and repair shared views with `bash tools/sync_agent_canon.sh link-root` when needed. |
| 3 | Move agent convenience installs out of `Dockerfile` and into shared `.devcontainer/post-create.sh` when they are not product dependencies. |
| 4 | Keep workspace-dependent Python package installation in `docker/install_python_dependencies.sh`. |
| 5 | Ensure Docker workflows checkout `vendor/agent-canon/` before shared devcontainer smoke. |
| 6 | Update `docker/README.md`, top-level README links, and workflow comments that still assume older ownership rules. |
| 7 | Run the validators listed below and record any skipped command with reason and owner. |

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
bash tools/sync_agent_canon.sh link-root
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

| PR | Merge | Rule change for downstream repositories |
| --- | --- | --- |
| #17 `9241cbd` | 2026-05-13 14:47 | Docker devcontainer CI must checkout AgentCanon before shared devcontainer smoke. The workflow checker rejects the old submodule-free assumption. |
| #16 `0de03e4` | 2026-05-13 14:28 | Hook, skill, eval, memory, issue, and improvement-guide evidence must accumulate through explicit files and workflow gates. |
| #14 `dfd0b6d` | 2026-05-13 13:29 | Nested Codex post-create setup belongs in the shared devcontainer path and runs after the workspace is available. |
| #13 `d679446` | 2026-05-13 13:36 | Helper inventory supports changed-file baseline mode; new helpers require reuse evidence and changed-scope inspection. |
| #12 `c5a7c77` | 2026-05-13 13:12 | GitHub-first custom modules and shared devcontainer ownership are the default; local Git mirrors are compatibility-only. |
| #11 `62d8342` | 2026-05-13 12:57 | Helper definitions must be inventoried and justified instead of added as untracked convenience code. |
| #10 `d8caa5b` | 2026-05-13 12:15 | Review backlog and repo-wide scans must degrade when `rg` is missing instead of assuming one local search tool. |
| #9 `2da3793` | 2026-05-13 12:01 | PR queue cleanup requires validation gates and authority evidence before mutation. |
| #8 `7f512e3` | 2026-05-13 11:50 | PR mutation authority is explicit. `gh` availability alone does not authorize merge, close, or branch delete. |
| #7 `0856d16` | 2026-05-13 11:06 | OOP hook alternate route payloads must be logged with unique evidence rather than disappearing into a generic pass/fail result. |

## Recent Template Rule Changes

The template repository currently has fewer than ten merged GitHub PRs, so this
table uses the latest ten rule-affecting `main` commits. Use it when reformatting
a template-derived repository that may still contain stale wording.

| Commit | Rule change for template-derived repositories |
| --- | --- |
| `d68f736` | Template now adopts the shared AgentCanon devcontainer and Agent Improvement Guide workflow. |
| `3715e3d` | Template pinned the AgentCanon operational issue and inspection proposal; issue evidence is part of workflow state. |
| `b5c8368` | GitHub CI installs `ripgrep`; repo-wide search tooling may prefer `rg` but must still document alternate route behavior where required. |
| `58d3e18` | AgentCanon snapshot sync: root shared views are repaired by sync tooling, not edited as independent truth surfaces. |
| `8ee9867` | AgentCanon snapshot sync: downstream template changes must carry the submodule pin evidence. |
| `d597611` | AgentCanon snapshot sync: template root views track the AgentCanon pin and must not assume subtree ownership. |
| `6c0dc6b` | Template pinned PR authority evidence from AgentCanon; branch and PR mutation require explicit workflow evidence. |
| `927f604` | Template pinned the PR authority proposal; GitHub operations are part of the documented agent workflow. |
| `8efa2ad` | Template pinned repo-cross inspection updates; search hits should be expanded into edit-scope dependency lists. |
| `669cc4d` | Template pinned the operational issue gate proposal; operational findings must have durable issue-file evidence. |

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
