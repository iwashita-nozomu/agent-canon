<!--
@dependency-start
contract reference
responsibility Provides a slide-style overview of the project template repository.
upstream design ../README.md repository overview
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface policy
upstream design ./template-github-remote.md template GitHub remote policy
upstream design ./agent-canon-github-remote.md AgentCanon GitHub remote policy
upstream design ./linux-wsl-host-requirements.md host runtime policy
downstream design ./README.md document index links this slide deck
@dependency-end
-->

# Project Template Overview Slides

## Reader Map

- Owns the slide-style overview of the project template repository.
- Main path: repository purpose, shape, AgentCanon model, GitHub policy,
  Actions/PR automation, Codex runtime, workflow discipline, dependency
  manifest policy, static analysis, Docker, Jupyter/results, template use, and
  review checklist.
- Read this for a presentation-oriented scan of the template rather than a
  complete operating manual.
- Boundary: detailed policy and commands remain in the linked repository,
  document, and runtime canon files.

## 1. What This Repository Is

- A reusable project template for code, experiments, documents, agent workflows, Docker runtime, and GitHub operations.
- The template keeps project-local state in the root repository.
- Shared agent rules and tooling live in AgentCanon.

## 2. Repository Shape

- `README.md`: reader-facing entrypoint.
- `AGENTS.md`: runtime entrypoint for Codex.
- `documents/`: durable project policy and operator guides.
- `docker/`: canonical container runtime, packs, Jupyter, and nested Codex.
- `tools/`: shared automation and validation entrypoints.
- `vendor/agent-canon/`: Git submodule pin to shared AgentCanon.

## 3. AgentCanon Model

- AgentCanon is consumed as a submodule pin, not a committed snapshot.
- Root symlink and copy surfaces are runtime views into the pinned AgentCanon commit.
- Shared canon changes should be made in the AgentCanon repository first, then the template pin is updated.
- Legacy subtree wording is compatibility-only and not the normal path.

## 4. GitHub Remote Policy

- Template canonical remote: `https://github.com/iwashita-nozomu/project_template.git`.
- AgentCanon canonical remote: `https://github.com/iwashita-nozomu/agent-canon.git`.
- PR evidence should record GitHub SHA and submodule pin SHA.

## 5. GitHub Actions And PR Automation

- Private AgentCanon submodule checkout requires `AGENT_CANON_REPO_TOKEN` or `AGENT_CANON_REPO_SSH_KEY`.
- Workflows checkout the template root with `submodules: false`.
- `.github/scripts/checkout_agent_canon_submodule.sh` initializes `vendor/agent-canon`, persists token or deploy-key auth for later same-job AgentCanon fetches, and fails with a precise remediation message when credentials are missing.
- GitHub PR automation should follow AgentCanon PR workflow and PR checklist surfaces.

## 6. Codex Runtime

- `.codex/config.toml` is the repo-shared Codex config surface.
- Hooks verify MCP inventory and goal-loop startup context.
- `goal.md` is repo-local durable goal state.
- Subagents are governed by runtime limits, explicit user permission, and run-bundle lifecycle policy.

## 7. Workflow Discipline

- Repo-changing work starts from a run bundle and user request contract.
- Implementation must be preceded by dependency intake, reuse survey, and design / review gates.
- Closeout requires dependency review, static analysis, diff-check evidence, validation, commit, push, and no unfinished task.
- Generated run artifacts belong under ignored `reports/agents/<run-id>/`.

## 8. Dependency Manifest Policy

- Human-authored text files carry `@dependency-start` / `@dependency-end` manifests near the top.
- Dependency review runs over the whole repo, not only the latest diff.
- Root symlink views and real AgentCanon source paths are classified separately.
- Graph checks validate self-reference and cycles from upstream / downstream sections.

## 9. Static Analysis And OOP

- Static tools are organized under language-oriented surfaces and integrated through review backlog scans.
- Python `Any`, hardcoded numbers, log helper naming, and OOP readability have mechanical checks.
- OOP findings are converted into backlog items with `path:line`, finding kind, boundary change, and validation evidence.

## 10. Docker And Devcontainer

- Docker is the canonical runtime, not a place to hardcode machine-local remote paths.
- `docker/packs/default.toml` defines build and smoke checks.
- Devcontainer compose is generated from the runtime pack.
- Host `~/.codex`, `~/.config/gh`, `~/.ssh`, and `SSH_AUTH_SOCK` are reused when available.

## 11. Jupyter And Results

- JupyterLab, notebook, ipykernel, Graphviz, and visualization helpers are part of the canonical container.
- `make docker-jupyter` starts host-browser JupyterLab on the configured port.
- Results are summarized through JSON, JSONL, Markdown, and visual artifacts with retention decisions.

## 12. Template Use

- Clone with `git clone --recurse-submodules`.
- Run `make agent-canon-ensure-latest` when the AgentCanon update surface is repairable; unrelated parent dirty state does not block submodule updates.
- Use `bash tools/sync_agent_canon.sh link-root` to repair shared runtime views.
- Run `make ci`, `tools/bin/agent-canon docs check`, and dependency review before closeout.

## 13. Review Checklist

- Confirm AgentCanon pin and `.gitmodules`.
- Confirm GitHub workflow credentials and PR templates.
- Confirm dependency manifests and generated report isolation.
- Confirm no stale subtree-only guidance remains in user-facing surfaces.
- Confirm final state is pushed to the intended canonical remote.
