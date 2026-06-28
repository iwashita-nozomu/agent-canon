<!--
@dependency-start
contract reference
responsibility Documents documents/ for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md documents ownership policy
upstream design ./shared-runtime-surfaces.toml machine-readable ownership manifest
downstream design ./algorithm-implementation-boundary.md algorithm math-to-code boundary policy
downstream design ./codex-configuration-reference.md Codex configuration reference
downstream design ./object-oriented-design.md general OOP coding policy
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream design ./github-first-module-and-devcontainer-policy.md GitHub-first module and devcontainer boundary policy
downstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
downstream design ./template-agent-canon-audit-resolution.md audit resolution ledger
downstream design ./tool-skill-routing-refactor.md short tool/skill routing policy
downstream design ./rust-agent-tool-migration.md Rust tool migration policy
downstream design ./structured-analysis/README.md structured prose and dependency analysis package boundary
downstream design ./prose-reasoning-graph/dsl-spec.md prose graph DSL contract
@dependency-end
-->

# documents/

`documents/README.md` is the root `documents/` index. Read it after the top-level
`README.md` when you need the root-owned document map. Use `agents/README.md`
for workflow / skill / runtime routing rather than treating this file as a
second agent hub.

`documents/` is still a mixed documentation directory. The root
`documents/README.md` stays repo-local after template clone. AgentCanon may seed
this file, but derived repositories own their local index.

## Reader Map

- Owns the root `documents/` index and the split between AgentCanon-owned,
  template-owned, project-owned, and generated documentation.
- Main path: Ownership Matrix, Reader Routes, Coding Policy References,
  Template-Owned Active Contracts, and Tooling And Artifact References.
- Read this after the top-level `README.md` when deciding which document owns a
  repository policy or guide.
- Boundary: workflow, skill, and runtime routing belong to `agents/README.md`,
  not this document index.

## Ownership Matrix

| Class | Examples | Edit source |
| --- | --- | --- |
| AgentCanon-owned shared policy symlink | coding conventions, review process, workflow-supporting policies, shared templates, tool docs | `vendor/agent-canon/documents/` |
| Template-owned active contract | bootstrap, host requirements, server contract, remote execution contract, template remote policy | root `documents/` regular files |
| Project-owned docs | architecture notes, project-specific design specs, implementation contracts | root `documents/` regular files |
| Generated or run artifacts | agent reports, experiment outputs, logs | `reports/` or `experiments/`, not `documents/` |

If a file is an AgentCanon-owned symlink, edit the source under
`vendor/agent-canon/` and repair the root view with
`bash tools/sync_agent_canon.sh link-root`. If a file is a template-owned active
contract, edit the root regular file.

## Reader Routes

This file is an index, but it should not force a reader through every link.
Choose the row that matches the current problem, then open only the listed
entrypoint and its directly referenced source packet.

| Problem | Start Here | Why |
| --- | --- | --- |
| Root view, symlink, copy, or template ownership is unclear | [Shared Runtime Surfaces](./SHARED_RUNTIME_SURFACES.md) | Defines owner classes and root-view repair rules; the TOML manifest is the machine-readable companion. |
| A vendored AgentCanon checkout, parent pin, or update branch is stale | [AgentCanon Update Route](./agent-canon-update-route.md) | Routes latest, branch / PR, TODO, rollback, and parent pin flows without reading every update doc. |
| Validation scope is unclear | [Runtime Profiles And Check Matrix](./runtime-profiles-and-check-matrix.md) | Maps changed path and risk class to the active checks. |
| Tool / skill routing, tool placement, or Rust migration is unclear | [Tool And Skill Routing Refactor](./tool-skill-routing-refactor.md) | Leads to tool catalog, short command names, and Rust CLI migration boundaries. |
| Structured prose, dependency graph, or document-canon analysis is needed | [Structured Analysis](./structured-analysis/) | Entry for document inventory, prose graph, report contracts, and SQLite-backed analysis. |
| Codex CLI, hooks, MCP, skills, or subagents need runtime configuration context | [Codex Configuration Reference](./codex-configuration-reference.md) | Keeps runtime config detail in one place instead of spreading copies across README files. |
| A derived repo is being bootstrapped or repaired | [Derived Repository Bootstrap Runbook](./derived-repo-bootstrap-runbook.md) | Shortest safe onboarding path for repos that vendor AgentCanon. |
| Maintenance issue labels or prompt / skill eval policy are needed | [Issue Label Taxonomy](./issue-label-taxonomy.md), [Prompt And Skill Evaluation Checklist](./prompt-skill-evaluation-checklist.md) | Operational governance entrypoints, not general first-read docs. |
| A negative public API or capability claim needs evidence | [API Surface Traversal Policy](./api-surface-traversal-policy.md) | Defines traversal evidence before saying a surface is absent. |

Compatibility and evidence appendices remain available, but they are not part of
the first-read path: `agent-canon-parent-repo-latest-checklist.md`,
`agent-canon-submodule-rollback.md`,
`template-agent-canon-audit-resolution.md`,
`github-first-module-and-devcontainer-policy.md`,
`agent-canon-github-remote.md`, `rust-agent-tool-migration.md`,
`prose-reasoning-graph/`, and `runtime-profiles-and-check-matrix.json`.

## Coding Policy References

- [Algorithm Implementation Boundary Policy](./algorithm-implementation-boundary.md):
  math/specification boundary, implementation boundary, change classes, and
  review gates.
- [Object-Oriented Design Policy](./object-oriented-design.md): class,
  dataclass, Protocol, composition, and inheritance policy.
- [Python Coding Conventions](./coding-conventions-python.md): Python-specific
  implementation rules.
- [Project Coding Conventions](./coding-conventions-project.md): project-wide
  environment, dependency, and runtime rules.

## Template-Owned Active Contracts

These files should be regular files in the template or derived repo root:

- [Template Bootstrap](./template-bootstrap.md)
- [Template GitHub Remote](./template-github-remote.md)
- [Linux / WSL Host Requirements](./linux-wsl-host-requirements.md)
- [Server Host Contract](./server-host-contract.md)
- [Remote Execution Repo Contract](./remote-execution-repo-contract.md)

AgentCanon provides reusable contract templates under [templates/](./templates/),
but the active contract for a derived repo belongs to that repo.

## Tooling And Artifact References

- [Result Log Retention And Visualization](./result-log-retention-and-visualization.md):
  run result, summary, visualization artifact, and retention rules.
- [Repo-Local Tool Imports](./repo-local-tool-imports.md): disposition ledger for
  tools that grow in derived repos before AgentCanon promotion.
